#!/usr/bin/env python3
"""Build and verify a canonical Easyrocks release without publishing it."""

from email.parser import BytesParser
from hashlib import sha256, sha512
from importlib import metadata
from pathlib import Path, PurePosixPath
import copy
import gzip
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / 'release'
REQUIRED_TOOLS = (
    'pip',
    'build',
    'setuptools',
    'wheel',
    'twine',
    'msgpack',
    'rocksdict',
    'google-crc32c',
)
IGNORED_NAMES = (
    '.DS_Store',
    '.git',
    '.venv',
    'ENV',
    'build',
    'dist',
    'env',
    'release',
    'rocksdb',
    'venv',
    '*.egg-info',
    '*.pyc',
    '__pycache__',
    '.mypy_cache',
    '.pytest_cache',
    '.ruff_cache',
)
IGNORED = shutil.ignore_patterns(*IGNORED_NAMES)
EXPECTED_NAME = 'easyrocks'
EXPECTED_VERSION = '4.2610.0'
EXPECTED_PYTHON = '>=3.10,<4.0'
EXPECTED_LICENSE = 'GPL-3.0-only'
EXPECTED_REQUIREMENTS = {
    'msgpack<2.0.0,>=1.2.1',
    'rocksdict<1.0.0,>=0.3.29',
    'google-crc32c<2.0.0,>=1.7.1',
}
SOURCE_INPUT_DIGEST_ALGORITHM = 'sha256-framed-path-content-v1'


def run(arguments, *, cwd=None, environment=None):
    subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        check=True,
    )


def expected_tool_versions():
    versions = {}
    expression = re.compile(
        r'^([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.+-]+)\s*$'
    )
    for line in (ROOT / 'requirements-dev.txt').read_text().splitlines():
        match = expression.fullmatch(line.strip())
        if match:
            versions[match.group(1).lower()] = match.group(2)
    missing = set(REQUIRED_TOOLS) - set(versions)
    if missing:
        raise RuntimeError(
            'requirements-dev.txt lacks exact release tool pins: '
            + ', '.join(sorted(missing))
        )
    return versions


def verify_toolchain():
    expected = expected_tool_versions()
    for package in REQUIRED_TOOLS:
        actual = metadata.version(package)
        if actual != expected[package]:
            raise RuntimeError(
                f'{package} must be {expected[package]}, got {actual}'
            )
    return expected


def digest(path, algorithm):
    value = algorithm()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def source_input_digest(directory):
    value = sha256()
    value.update(b'python-release-source-input-v1\0')
    paths = sorted(
        path for path in directory.rglob('*') if path.is_file()
    )
    for path in paths:
        relative = path.relative_to(directory).as_posix().encode('utf-8')
        size = path.stat().st_size
        value.update(len(relative).to_bytes(8, 'big'))
        value.update(relative)
        value.update(size.to_bytes(8, 'big'))
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                value.update(chunk)
    return value.hexdigest()


def vcs_identifier(environment_name):
    value = os.environ.get(environment_name)
    if value is None:
        return 'unavailable'
    if re.fullmatch(r'[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?', value) is None:
        raise RuntimeError(
            f'{environment_name} must be a 40- or 64-digit hex id.'
        )
    return value.lower()


def artifacts(directory):
    candidates = sorted(
        path for path in directory.iterdir() if path.is_file()
    )
    wheels = [path for path in candidates if path.suffix == '.whl']
    sdists = [
        path for path in candidates if path.name.endswith('.tar.gz')
    ]
    if len(wheels) != 1 or len(sdists) != 1 or len(candidates) != 2:
        raise RuntimeError(
            'A release build must contain exactly one wheel and one sdist.'
        )
    return wheels[0], sdists[0]


def normalize_sdist(path, epoch):
    members = []
    with tarfile.open(path, mode='r:gz') as source:
        for original in source.getmembers():
            member_path = PurePosixPath(original.name)
            if member_path.is_absolute() or '..' in member_path.parts:
                raise RuntimeError('The sdist contains an unsafe path.')
            if not (original.isdir() or original.isfile()):
                raise RuntimeError('The sdist contains a non-file member.')
            member = copy.copy(original)
            member.mtime = epoch
            member.uid = 0
            member.gid = 0
            member.uname = ''
            member.gname = ''
            member.pax_headers = {}
            content = None
            if member.isfile():
                extracted = source.extractfile(original)
                if extracted is None:
                    raise RuntimeError('Could not read an sdist member.')
                content = extracted.read()
            members.append((member, content))

    with path.open('wb') as target:
        with gzip.GzipFile(
            filename='',
            mode='wb',
            fileobj=target,
            mtime=epoch,
        ) as compressed:
            with tarfile.open(
                fileobj=compressed,
                mode='w',
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for member, content in members:
                    archive.addfile(
                        member,
                        None if content is None else io.BytesIO(content),
                    )


def wheel_content(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError('The wheel contains duplicate members.')
        return {
            name: archive.read(name)
            for name in sorted(names)
            if not name.endswith('/')
        }


def verify_wheel(path):
    expected_filename = f'{EXPECTED_NAME}-{EXPECTED_VERSION}-py3-none-any.whl'
    if path.name != expected_filename:
        raise RuntimeError(f'Unexpected wheel filename: {path.name}')
    content = wheel_content(path)
    forbidden = [
        name for name in content
        if '__pycache__' in name or name.endswith(('.pyc', '.pyo'))
        or Path(name).suffix.lower() in ('.md', '.markdown', '.mdown')
        or Path(name).name.lower().startswith('readme')
    ]
    if forbidden:
        raise RuntimeError('The wheel contains documentation or generated Python files.')

    required_modules = {
        'easyrocks/__init__.py',
        'easyrocks/_version.py',
        'easyrocks/easyrocks.py',
        'easyrocks/utils.py',
    }
    if not required_modules.issubset(content):
        raise RuntimeError('The wheel omits an Easyrocks module.')

    metadata_files = [
        value
        for name, value in content.items()
        if name.endswith('.dist-info/METADATA')
    ]
    if len(metadata_files) != 1:
        raise RuntimeError('The wheel must contain one METADATA file.')
    parsed = BytesParser().parsebytes(metadata_files[0])
    if parsed['Name'] != EXPECTED_NAME:
        raise RuntimeError('Unexpected package name in wheel metadata.')
    if parsed['Version'] != EXPECTED_VERSION:
        raise RuntimeError('Unexpected version in wheel metadata.')
    if parsed['Requires-Python'] != EXPECTED_PYTHON:
        raise RuntimeError('Unexpected Requires-Python in wheel metadata.')
    if parsed['License-Expression'] != EXPECTED_LICENSE:
        raise RuntimeError('Unexpected license expression in metadata.')
    requirements = {
        requirement.replace(' ', '')
        for requirement in parsed.get_all('Requires-Dist', [])
    }
    if requirements != EXPECTED_REQUIREMENTS:
        raise RuntimeError(
            f'Unexpected runtime requirements: {sorted(requirements)}'
        )


def verify_sdist(path):
    expected_filename = f'{EXPECTED_NAME}-{EXPECTED_VERSION}.tar.gz'
    if path.name != expected_filename:
        raise RuntimeError(f'Unexpected sdist filename: {path.name}')
    expected_root = f'{EXPECTED_NAME}-{EXPECTED_VERSION}'
    required = {
        f'{expected_root}/LICENSE',
        f'{expected_root}/easyrocks/_version.py',
        f'{expected_root}/easyrocks/easyrocks.py',
        f'{expected_root}/easyrocks/utils.py',
        f'{expected_root}/pyproject.toml',
        f'{expected_root}/setup.py',
        f'{expected_root}/tests/test_rocksdb.py',
        f'{expected_root}/tests/test_utils.py',
    }
    with tarfile.open(path, mode='r:gz') as archive:
        names = {member.name for member in archive.getmembers()}
    if any(Path(name).suffix.lower() in ('.md', '.markdown', '.mdown')
           or Path(name).name.lower().startswith('readme') for name in names):
        raise RuntimeError('The sdist contains Markdown or README files.')
    if not required.issubset(names):
        missing = ', '.join(sorted(required - names))
        raise RuntimeError(f'The sdist omits required files: {missing}')


def smoke_wheel(wheel, *, cwd, environment):
    script = r'''
import pickle
import sys
from tempfile import TemporaryDirectory
sys.path.insert(0, sys.argv[1])

import easyrocks
from easyrocks import RocksDB

assert easyrocks.__version__ == '4.2610.0'
with TemporaryDirectory(dir='.') as directory:
    database = RocksDB(directory + '/db', safe_serialization=True)
    try:
        value = {'block': {'items': [1, b'bytes'], 'active': True}}
        database.put(b'current', value)
        database.db.put(b'legacy', pickle.dumps(value, protocol=5))
        database.backup(directory + '/backup')
        database.delete(b'current')
        database.restore_backup(directory + '/backup')
        assert database.get(b'current') == value
        assert database.get(b'legacy') == value
    finally:
        database.close()
'''
    run(
        [sys.executable, '-c', script, str(wheel)],
        cwd=cwd,
        environment=environment,
    )


def main():
    raw_epoch = os.environ.get('SOURCE_DATE_EPOCH')
    if not raw_epoch or not raw_epoch.isdecimal():
        raise RuntimeError(
            'Set SOURCE_DATE_EPOCH to the chosen source snapshot epoch.'
        )
    if int(raw_epoch) < 315532800:
        raise RuntimeError('SOURCE_DATE_EPOCH must be 1980-01-01 or later.')
    vcs_revision = vcs_identifier('ARTIFACT_VCS_REVISION')
    vcs_tree = vcs_identifier('ARTIFACT_VCS_TREE')
    tool_versions = verify_toolchain()
    environment = dict(os.environ)
    environment['SOURCE_DATE_EPOCH'] = raw_epoch
    environment['PYTHONHASHSEED'] = '0'

    with tempfile.TemporaryDirectory(
        prefix='easyrocks-release-'
    ) as temporary_name:
        temporary = Path(temporary_name)
        outputs = []
        source_input_sha256 = None
        for number in (1, 2):
            source = temporary / f'source-{number}'
            output = temporary / f'build-{number}'
            shutil.copytree(ROOT, source, ignore=IGNORED)
            candidate_digest = source_input_digest(source)
            if source_input_sha256 is None:
                source_input_sha256 = candidate_digest
            elif candidate_digest != source_input_sha256:
                raise RuntimeError('Source exports are not reproducible.')
            output.mkdir()
            run(
                [
                    sys.executable,
                    '-m',
                    'build',
                    '--no-isolation',
                    '--outdir',
                    str(output),
                ],
                cwd=source,
                environment=environment,
            )
            wheel, source_distribution = artifacts(output)
            normalize_sdist(source_distribution, int(raw_epoch))
            verify_wheel(wheel)
            verify_sdist(source_distribution)
            outputs.append(output)

        first = artifacts(outputs[0])
        second = artifacts(outputs[1])
        if [path.name for path in first] != [path.name for path in second]:
            raise RuntimeError('Repeated builds produced different names.')
        for left, right in zip(first, second):
            if digest(left, sha256) != digest(right, sha256):
                raise RuntimeError(
                    f'{left.name} is not reproducible across two builds.'
                )

        run(
            [
                sys.executable,
                '-m',
                'twine',
                'check',
                *(str(path) for path in first),
            ],
            environment=environment,
        )

        original_wheel, source_distribution = first
        rebuilt = temporary / 'rebuilt-wheel'
        rebuilt.mkdir()
        run(
            [
                sys.executable,
                '-m',
                'pip',
                'wheel',
                '--disable-pip-version-check',
                '--no-deps',
                '--no-build-isolation',
                '--wheel-dir',
                str(rebuilt),
                str(source_distribution),
            ],
            environment=environment,
        )
        rebuilt_wheels = list(rebuilt.glob('*.whl'))
        if len(rebuilt_wheels) != 1:
            raise RuntimeError('The sdist did not rebuild one wheel.')
        if wheel_content(original_wheel) != wheel_content(
            rebuilt_wheels[0]
        ):
            raise RuntimeError(
                'The wheel rebuilt from the sdist has different contents.'
            )
        smoke_wheel(
            original_wheel,
            cwd=temporary,
            environment=environment,
        )

        if RELEASE.is_symlink():
            raise RuntimeError('The release path must not be a symlink.')
        if RELEASE.exists():
            shutil.rmtree(RELEASE)
        RELEASE.mkdir()
        final_artifacts = []
        for path in first:
            target = RELEASE / path.name
            shutil.copy2(path, target)
            final_artifacts.append(target)

        for algorithm, filename in (
            (sha256, 'SHA256SUMS'),
            (sha512, 'SHA512SUMS'),
        ):
            lines = [
                f'{digest(path, algorithm)}  {path.name}\n'
                for path in sorted(final_artifacts)
            ]
            (RELEASE / filename).write_text(''.join(lines))

        information = [
            'Canonical release candidate; do not rebuild before publishing.',
            f'vcs_revision={vcs_revision}',
            f'vcs_tree={vcs_tree}',
            (
                'vcs_scope=base checkout identifiers; working-tree content '
                'is covered by source_input_sha256'
            ),
            'provenance_claim=build receipt; not a cryptographic attestation',
            f'SOURCE_DATE_EPOCH={raw_epoch}',
            (
                'source_input_digest_algorithm='
                f'{SOURCE_INPUT_DIGEST_ALGORITHM}'
            ),
            'source_input_scope=sorted regular-file paths and bytes',
            'source_input_exclusions=' + ','.join(IGNORED_NAMES),
            f'source_input_sha256={source_input_sha256}',
            f'python={sys.version.split()[0]}',
        ]
        information.extend(
            f'{package}={tool_versions[package]}'
            for package in REQUIRED_TOOLS
        )
        information.extend(
            f'artifact_sha256[{path.name}]={digest(path, sha256)}'
            for path in sorted(final_artifacts)
        )
        information.extend([
            'wheel_metadata=verified',
            'sdist_contents=verified',
            'sdist_rebuilt_wheel=content-identical',
            'smoke_import=real-rocksdict-backend',
            'upload=not_performed',
            'download=not_performed',
        ])
        (RELEASE / 'RELEASE_INFO.txt').write_text(
            '\n'.join(information) + '\n'
        )

    for path in sorted(RELEASE.iterdir()):
        print(path)


if __name__ == '__main__':
    main()
