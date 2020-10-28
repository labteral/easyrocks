#!/usr/bin/env python
# -*- coding: utf-8 -*-

from . import utils
from rocksdb import *
from rocksdb import DB as RDB, Options

ALLOWED_KEY_TYPES = (int, str)


class RocksDB:
    def __init__(self, path: str = './rocksdb-data', opts: dict = None, read_only: bool = False):
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
    def db(self) -> RDB:
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
            del self._db

        self._db = RDB(self._path, rocks_opts, read_only=read_only)

    def put(self, key, value, write_batch=None):
        if not isinstance(key, ALLOWED_KEY_TYPES):
            raise TypeError

        if value is None:
            raise ValueError

        key_bytes = utils._get_key_bytes(key)
        value_bytes = utils.to_bytes(value)

        if write_batch is not None:
            write_batch.put(key_bytes, value_bytes)
        else:
            self._db.put(key_bytes, value_bytes, sync=True)

    def get(self, key):
        key_bytes = utils._get_key_bytes(key)
        value_bytes = self._db.get(key_bytes)

        if value_bytes is not None:
            return utils.to_object(value_bytes)

    def exists(self, key):
        if self.get(key) is not None:
            return True
        return False

    def delete(self, key):
        key_bytes = utils.str_to_bytes(key)
        self._db.delete(key_bytes, sync=True)

    def commit(self, write_batch):
        if write_batch is not None:
            self._db.write(write_batch, sync=True)

    def scan(self, prefix=None, start_key=None, end_key=None, reversed_scan=False):
        iterator = self._db.iterkeys()

        if prefix is None and start_key is None:
            if reversed_scan:
                iterator.seek_to_last()
            else:
                iterator.seek_to_first()
        else:
            if prefix is not None:
                prefix_bytes = utils.str_to_bytes(prefix)
            else:
                prefix_bytes = utils.str_to_bytes(start_key)
            iterator.seek(prefix_bytes)

        if reversed_scan:
            iterator = reversed(iterator)

        for key_bytes in iterator:
            key = utils.bytes_to_str(key_bytes)

            if prefix is not None and key[:len(prefix)] != prefix:
                return

            if end_key is not None and key > end_key:
                return

            value_bytes = self._db.get(key_bytes)
            value = utils.to_object(value_bytes)
            yield key, value

    def close(self):
        self._db.close()


# Backward compatibility
class DB(RocksDB):
    pass