#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gc
from . import utils
from rocksdb import *

ALLOWED_KEY_TYPES = (int, str, bytes)


class RocksDB:
    def __init__(self, path: str = './rocksdb', opts: dict = None, read_only: bool = False):
        self._path = path

        if opts is None:
            opts = {}
        self._opts = opts

        self._read_only = read_only
        self.reload(read_only=read_only)

    @property
    def path(self) -> str:
        return self._path

    @property
    def opts(self) -> dict:
        return dict(self._opts)

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def db(self) -> DB:
        return self._db

    def reload(self, opts: dict = None, read_only: bool = None):
        if opts is None:
            opts = self._opts

        if read_only is None:
            read_only = self._read_only

        rocks_opts = Options(create_if_missing=True)
        for key, value in opts.items():
            setattr(rocks_opts, key, value)

        if hasattr(self, '_db'):
            self.close()

        self._db = DB(self._path, rocks_opts, read_only=read_only)

    def put(self, key, value, write_batch=None):
        if not isinstance(key, ALLOWED_KEY_TYPES):
            raise TypeError

        if value is None:
            raise ValueError

        key_bytes = utils._get_key_bytes(key)
        value_bytes = utils.pack(value)

        if write_batch is not None:
            write_batch.put(key_bytes, value_bytes)
        else:
            self._db.put(key_bytes, value_bytes, sync=True)

    def get(self, key):
        key_bytes = utils._get_key_bytes(key)
        value_bytes = self._db.get(key_bytes)

        if value_bytes is not None:
            return utils.unpack(value_bytes)

    def exists(self, key):
        if self.get(key) is not None:
            return True
        return False

    def delete(self, key):
        key = utils.to_padded_bytes(key)
        self._db.delete(key, sync=True)

    def commit(self, write_batch):
        if write_batch is not None:
            self._db.write(write_batch, sync=True)

    def scan(self, prefix=None, start_key=None, stop_key=None, reversed_scan=False):
        prefix = utils.to_padded_bytes(prefix)
        start_key = utils.to_padded_bytes(start_key)
        stop_key = utils.to_padded_bytes(stop_key)

        iterator = self._db.iterkeys()

        if prefix is None and start_key is None:
            if reversed_scan:
                iterator.seek_to_last()
            else:
                iterator.seek_to_first()
        else:
            if not prefix and start_key:
                prefix = start_key
            iterator.seek(prefix)

        if reversed_scan:
            iterator = reversed(iterator)

        for key in iterator:
            if prefix is not None and key[:len(prefix)] != prefix:
                return

            if stop_key is not None and key > stop_key:
                return

            value_bytes = self._db.get(key)
            value = utils.unpack(value_bytes)
            yield key, value

    def close(self):
        del self._db
        gc.collect()

    def backup(self, path: str = './rocksdb-backup'):
        backup_engine = BackupEngine(path)
        backup_engine.create_backup(self._db, flush_before_backup=True)

    @staticmethod
    def backup_info(path: str):
        backup_engine = BackupEngine(path)
        return backup_engine.get_backup_info()

    @staticmethod
    def delete_backup(path: str, backup_id: int = None):
        backup_engine = BackupEngine(path)
        return backup_engine.delete_backup(backup_id)

    def restore_backup(self, path: str, backup_id: int = None):
        self.close()
        backup_engine = BackupEngine(path)
        if backup_id is None:
            backup_engine.restore_latest_backup(self._path, self._path)
        else:
            backup_engine.restore_backup(backup_id, self._path, self._path)
        self.reload()