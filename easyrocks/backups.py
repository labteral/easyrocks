"""RocksDB BackupEngine v1 archives, created from raw Rocksdict checkpoints.

Files are private to each revision; legacy shared/shared_checksum SSTs are
also readable. The metadata rename is the commit point of a new backup.
"""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from tempfile import TemporaryDirectory
import time

from google_crc32c import Checksum
from rocksdict import AccessType, Options, Rdict


def disjoint(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    if left == right or left in right.parents or right in left.parents:
        raise ValueError('Database and backup paths must not overlap')


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def checksum(path):
    digest = Checksum()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return int.from_bytes(digest.digest(), 'big')


@contextmanager
def locked(path):
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f'Backup directory does not exist: {root}')
    # Lock the directory itself: restoring a read-only archive must not need
    # to create a lock file inside it.
    descriptor = os.open(root, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield root
    finally:
        os.close(descriptor)


def _file(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe backup filename')
    candidate = root / path
    linked = any((root.joinpath(*path.parts[:index])).is_symlink()
                 for index in range(1, len(path.parts) + 1))
    if (not candidate.is_file() or linked
            or not candidate.resolve().is_relative_to(root.resolve())):
        raise ValueError(f'Missing or unsafe backup file: {relative}')
    return candidate


def _entries(root, backup_id):
    meta = _file(root, f'meta/{backup_id}')
    lines = meta.read_text(encoding='utf-8').splitlines()
    if len(lines) < 3 or lines[0].startswith('schema_version'):
        raise ValueError('Unsupported or incomplete BackupEngine metadata')
    timestamp, sequence = int(lines.pop(0)), int(lines.pop(0))
    if timestamp < 0 or sequence < 0:
        raise ValueError('Invalid backup header')
    if lines[0].startswith('metadata '):
        bytes.fromhex(lines.pop(0).split(' ', 1)[1])
    if not lines:
        raise ValueError('Missing backup file count')
    count = int(lines.pop(0))
    if count != len(lines) or count < 1:
        raise ValueError('Incomplete backup file list')
    files = []
    names = set()
    for line in lines:
        parts = line.split()
        if len(parts) != 3 or parts[1] != 'crc32':
            raise ValueError('Invalid backup checksum record')
        relative, _, expected = parts
        path = PurePosixPath(relative)
        if path.parts[0] == 'private':
            if len(path.parts) != 3 or path.parts[1] != str(backup_id):
                raise ValueError('Invalid private backup path')
            name = path.name
        elif path.parts[0] in ('shared', 'shared_checksum'):
            if len(path.parts) != 2:
                raise ValueError('Invalid shared backup path')
            name = re.sub(r'_.*(?=\.(?:sst|blob)$)', '', path.name)
        else:
            raise ValueError('Unrecognized backup file layout')
        expected = int(expected)
        if name in names or not 0 <= expected <= 0xffffffff:
            raise ValueError('Duplicate file or invalid CRC32C')
        names.add(name)
        files.append((_file(root, relative), name, expected))
    if 'CURRENT' not in names:
        raise ValueError('Backup has no CURRENT file')
    return timestamp, files


def _ids(root):
    ids = sorted(int(p.name) for p in (root / 'meta').glob('*')
                 if p.name.isdecimal() and p.is_file())
    # Read checkpoints emitted by the earlier migration candidate as id 1.
    if (root / 'CURRENT').is_file():
        ids = sorted(set(ids) | {1})
    return ids


def _select(root, backup_id):
    ids = _ids(root)
    if not ids:
        raise ValueError('No backups found')
    if backup_id is None:
        backup_id = ids[-1]
    if type(backup_id) is not int or backup_id not in ids:
        raise ValueError(f'Unknown backup id: {backup_id}')
    return backup_id


def _revision(root, backup_id):
    if backup_id == 1 and (root / 'CURRENT').is_file():
        files = [(_file(root, p.name), p.name, None) for p in root.iterdir()
                 if p.is_file() and not p.name.startswith('.')]
        return int((root / 'CURRENT').stat().st_mtime), files
    return _entries(root, backup_id)


def info(path):
    root = Path(path)
    return [dict(backup_id=bid, timestamp=timestamp,
                 size=sum(p.stat().st_size for p, _, _ in files))
            for bid in _ids(root)
            for timestamp, files in [_revision(root, bid)]]


def validate(path):
    if not (path / 'CURRENT').is_file():
        raise ValueError('Backup has no CURRENT file')
    options = Options(raw_mode=True)
    options.create_if_missing(False)
    database = Rdict(str(path), options, access_type=AccessType.read_only())
    try:
        # A full raw scan checks SST checksums, including checkpoint-only
        # input.
        for _ in database.items():
            pass
        return database.latest_sequence_number()
    finally:
        database.close()


def create(database, path, checkpoint):
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    with locked(root):
        for name in ('private', 'meta'):
            directory = root / name
            if directory.is_symlink():
                raise ValueError(f'Unsafe backup directory: {directory}')
            directory.mkdir(exist_ok=True)
        sync_directory(root)
        # An orphan private directory from a failed backup reserves its ID too.
        ids = _ids(root) + [int(p.name) for p in (root / 'private').glob('*')
                            if p.name.isdecimal()]
        bid = max(ids, default=0) + 1
        if bid > 0xffffffff:
            raise OverflowError('BackupEngine ID limit reached')
        private = root / 'private' / str(bid)
        database.flush()
        with TemporaryDirectory(prefix='.backup-', dir=root) as temporary:
            staged = Path(temporary) / 'checkpoint'
            checkpoint(database).create_checkpoint(str(staged))
            sequence = validate(staged)
            files = sorted(p for p in staged.iterdir()
                           if p.name != 'rocksdict-config.json')
            records = []
            for file in files:
                if not file.is_file() or file.is_symlink():
                    raise ValueError('Unexpected checkpoint entry')
                records.append(f'private/{bid}/{file.name} crc32 '
                               f'{checksum(file)}\n')
                with file.open('rb') as stream:
                    os.fsync(stream.fileno())
            # Rocksdict config is not a RocksDB file. Raw mode is explicit on
            # restore, so omit it from native BackupEngine-compatible archives.
            (staged / 'rocksdict-config.json').unlink(missing_ok=True)
            sync_directory(staged)
            staged.rename(private)
            sync_directory(private.parent)
            meta = Path(temporary) / 'metadata'
            with meta.open('w') as output:
                output.write(f'{int(time.time())}\n'
                             f'{sequence}\n'
                             f'{len(records)}\n' + ''.join(records))
                output.flush()
                os.fsync(output.fileno())
            meta.rename(root / 'meta' / str(bid))
            sync_directory(root / 'meta')


def copy_backup(path, backup_id, destination):
    with locked(path) as root:
        bid = _select(root, backup_id)
        _, files = _revision(root, bid)
        destination.mkdir()
        for source, name, expected in files:
            target = destination / name
            shutil.copyfile(source, target)
            if expected is not None and checksum(target) != expected:
                raise ValueError(f'Backup checksum mismatch: {name}')
            with target.open('rb') as stream:
                os.fsync(stream.fileno())


def delete(path, backup_id):
    if backup_id is None:
        raise TypeError('Deleting a backup requires an explicit backup ID')
    with locked(path) as root:
        bid = _select(root, backup_id)
        _, files = _revision(root, bid)
        if bid == 1 and (root / 'CURRENT').is_file():
            (root / 'CURRENT').unlink()
            for file, _, _ in files:
                file.unlink(missing_ok=True)
        else:
            (root / 'meta' / str(bid)).unlink()
            sync_directory(root / 'meta')
            # Keep the empty private directory as an ID reservation. Shared
            # files may belong to another legacy backup and are never removed.
            for file, _, _ in files:
                if file.parent == root / 'private' / str(bid):
                    file.unlink()
