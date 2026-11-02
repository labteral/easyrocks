#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gc
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Generator

from rocksdict import (AccessType, BlockBasedOptions, Checkpoint, ChecksumType,
                       DBCompressionType,
                       FifoCompactOptions, Options, Rdict,
                       UniversalCompactOptions, WriteOptions)
from rocksdict import WriteBatch as _WriteBatch

from . import utils
from . import backups


def WriteBatch(raw_mode: bool = True):
    """Return a Rocksdict ``WriteBatch`` matching the database raw mode.

    Rocksdict batches default to its own value encoder, which rejects the
    MessagePack bytes Easyrocks stores, so raw mode is the only safe default.
    """
    return _WriteBatch(raw_mode=raw_mode)


class CompressionType:
    """Compatibility shim for python-rocksdb's ``CompressionType``."""

    no_compression = DBCompressionType.none()
    snappy_compression = DBCompressionType.snappy()
    zlib_compression = DBCompressionType.zlib()
    bz2_compression = DBCompressionType.bz2()
    lz4_compression = DBCompressionType.lz4()
    lz4hc_compression = DBCompressionType.lz4hc()
    zstd_compression = DBCompressionType.zstd()


#: python-rocksdb option name -> rocksdict setter.  Keys not listed here are
#: resolved as ``<key>`` or ``set_<key>`` when rocksdict exposes them.
_OPTION_SETTERS = {
    'compression': 'set_compression_type',
}

#: Nested option structs.  python-rocksdb accepts a plain dict, rocksdict
#: wants the corresponding object passed to its own setter.
_NESTED_OPTION_SETTERS = {
    'compaction_options_universal': (
        UniversalCompactOptions, 'set_universal_compaction_options'),
    'compaction_options_fifo': (
        FifoCompactOptions, 'set_fifo_compaction_options'),
}


def _apply_option(options: Options, key: str, value):
    nested = _NESTED_OPTION_SETTERS.get(key)
    if nested is not None:
        option_class, setter_name = nested
        if type(value) is not dict:
            raise TypeError(f'{key} must be a dict')
        nested_options = option_class()
        for nested_key, nested_value in value.items():
            if not hasattr(nested_options, nested_key):
                raise ValueError(f'unsupported {key} field: {nested_key}')
            setattr(nested_options, nested_key, nested_value)
        getattr(options, setter_name)(nested_options)
        return

    setter = _OPTION_SETTERS.get(key)
    if setter is None:
        setter = key if hasattr(options, key) else f'set_{key}'
    method = getattr(options, setter, None)
    if method is None:
        raise ValueError(f'unsupported RocksDB option: {key}')
    method(value)


class _RawIterator:
    """python-rocksdb style iterator over a Rocksdict database.

    Consumers such as synced, stopover, txlog and graphn's own tests reach the
    raw handle through ``RocksDB.db`` and drive it with
    ``seek_to_first``/``seek``/``seek_to_last``.  ``items`` yields raw
    ``(key, value)`` pairs the way python-rocksdb's ``iteritems`` did.
    """

    def __init__(self, database: Rdict, items: bool = False):
        self._items = items
        self._iterator = database.iter()
        self._backwards = False

    def seek_to_first(self):
        self._iterator.seek_to_first()

    def seek_to_last(self):
        self._iterator.seek_to_last()

    def seek(self, key: bytes):
        self._iterator.seek(key)

    def __reversed__(self):
        self._backwards = not self._backwards
        return self

    def __iter__(self):
        return self

    def __next__(self):
        if not self._iterator.valid():
            self._iterator.status()
            raise StopIteration
        value = ((self._iterator.key(), self._iterator.value())
                 if self._items else self._iterator.key())
        if self._backwards:
            self._iterator.prev()
        else:
            self._iterator.next()
        return value


class _RawDB:
    """Adapts Rocksdict to the python-rocksdb ``DB`` surface consumers use."""

    def __init__(self, database: Rdict):
        self._database = database

    def get(self, key):
        return self._database.get(key)

    def put(self, key, value, sync: bool = False):
        del sync  # every write is synced through the preset WriteOptions
        self._database.put(key, value)

    def delete(self, key, sync: bool = False):
        del sync
        self._database.delete(key)

    def write(self, write_batch, sync: bool = False):
        del sync
        self._database.write(write_batch)

    def iterkeys(self):
        return _RawIterator(self._database)

    def iteritems(self):
        return _RawIterator(self._database, items=True)


class RocksDB:

    ALLOWED_KEY_TYPES = set([bytes, type(None)])

    def __init__(self,
                 path: str = './rocksdb',
                 opts: Dict = None,
                 read_only: bool = False,
                 safe_serialization: bool = False):
        if not isinstance(safe_serialization, bool):
            raise TypeError('safe_serialization must be a boolean')
        self._path = path

        if opts is None:
            opts = {}
        self._opts = opts

        self._read_only = read_only
        self._safe_serialization = safe_serialization
        self.reload(read_only=read_only)

    @property
    def path(self) -> str:
        return self._path

    @property
    def opts(self) -> Dict:
        return dict(self._opts)

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def safe_serialization(self) -> bool:
        return self._safe_serialization

    @property
    def db(self) -> _RawDB:
        return self._raw

    def reload(self, opts: Dict = None, read_only: bool = None):
        # If a process died between the two restore renames, recover its
        # untouched original rather than create a new empty database.
        target = Path(self._path).resolve()
        previous = target.with_name(target.name + '.restore-previous')
        if previous.exists() and not target.exists():
            previous.rename(target)
        if opts is None:
            opts = self._opts

        if read_only is None:
            read_only = self._read_only

        # raw_mode is mandatory: without it Rocksdict applies its own value
        # encoder and rejects the MessagePack/Pickle bytes stored by previous
        # python-rocksdb deployments ("Unknown value type").  Easyrocks already
        # serializes every value itself through utils.pack.
        rocks_opts = Options(raw_mode=True)
        rocks_opts.create_if_missing(True)
        # Keep new SSTs readable by the RocksDB 6.x runtime used by legacy
        # deployments; Rocksdict's current footer/checksum defaults are newer.
        table = BlockBasedOptions()
        table.set_format_version(4)
        table.set_checksum_type(ChecksumType.crc32c())
        rocks_opts.set_block_based_table_factory(table)
        for key, value in opts.items():
            _apply_option(rocks_opts, key, value)

        if hasattr(self, '_db'):
            self.close()

        write_options = WriteOptions()
        write_options.sync = True

        access_type = (AccessType.read_only() if read_only
                       else AccessType.read_write())
        self._db = Rdict(
            self._path,
            options=rocks_opts,
            access_type=access_type)
        self._db.set_write_options(write_options)
        self._raw = _RawDB(self._db)

    def put(self, key: bytes, value, write_batch=None):
        if type(key) not in self.ALLOWED_KEY_TYPES:
            raise TypeError

        if value is None:
            raise ValueError

        value_bytes = utils.pack(
            value,
            safe=self._safe_serialization,
        )

        if write_batch is not None:
            write_batch.put(key, value_bytes)
        else:
            self._db.put(key, value_bytes)

    def get(self, key: bytes):
        if type(key) not in self.ALLOWED_KEY_TYPES:
            raise TypeError

        value_bytes = self._db.get(key)

        if value_bytes is not None:
            return utils.unpack(
                value_bytes,
                safe=self._safe_serialization,
            )

    def exists(self, key: bytes) -> bool:
        if self.get(key) is not None:
            return True
        return False

    def delete(self, key: bytes, write_batch: WriteBatch = None):
        if type(key) not in self.ALLOWED_KEY_TYPES:
            raise TypeError

        if write_batch is not None:
            write_batch.delete(key)
        else:
            self._db.delete(key)

    def commit(self, write_batch: WriteBatch):
        if write_batch is None:
            raise ValueError
        self._db.write(write_batch)

    def scan(self,
             prefix: bytes = None,
             start_key: bytes = None,
             stop_key: bytes = None,
             reversed_scan: bool = False) -> Generator:

        for key in [prefix, start_key, stop_key]:
            if type(key) not in self.ALLOWED_KEY_TYPES:
                raise TypeError

        from_key = prefix if prefix is not None else start_key
        if from_key is None:
            iterator = self._db.keys(backwards=reversed_scan)
        else:
            iterator = self._db.keys(
                backwards=reversed_scan, from_key=from_key)

        for key in iterator:
            if prefix is not None and key[:len(prefix)] != prefix:
                return

            if stop_key is not None and key > stop_key:
                return

            value_bytes = self._db.get(key)
            value = utils.unpack(
                value_bytes,
                safe=self._safe_serialization,
            )

            yield key, value

    def close(self):
        database = getattr(self, '_db', None)
        if database is None:
            return
        database.close()
        del self._db
        self._raw = None
        gc.collect()

    def backup(self, path: str = './rocksdb-backup'):
        """Append a verified backup without replacing an earlier revision."""
        backups.disjoint(self._path, path)
        backups.create(self._db, path, Checkpoint)

    @staticmethod
    def backup_info(path: str):
        return backups.info(path)

    @staticmethod
    def delete_backup(path: str, backup_id: int = None):
        backups.delete(path, backup_id)

    def restore_backup(self, path: str, backup_id: int = None):
        backups.disjoint(self._path, path)
        target = Path(self._path).resolve()
        previous = target.with_name(target.name + '.restore-previous')
        if previous.exists():
            raise FileExistsError(f'Previous restore retained at {previous}')
        with TemporaryDirectory(prefix=target.name + '.restore-',
                                dir=target.parent) as temporary:
            staged = Path(temporary) / 'database'
            backups.copy_backup(path, backup_id, staged)
            # Opening the staged database validates CURRENT/MANIFEST/SSTs.
            backups.validate(staged)
            backups.sync_directory(staged)
            self.close()
            try:
                target.rename(previous)
                staged.rename(target)
                backups.sync_directory(target.parent)
                self.reload()
            except BaseException:
                self.close()
                if previous.exists():
                    if target.exists():
                        target.rename(staged)
                    previous.rename(target)
                self.reload()
                raise
            shutil.rmtree(previous)
            backups.sync_directory(target.parent)
