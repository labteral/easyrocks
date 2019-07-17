#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rocksdb
from . import utils
from rocksdb import DB as RocksDB, Options, WriteBatch

ALLOWED_KEY_TYPES = (int, str)


class DB:
    def __init__(self, path='./rocksdb', opts=None, read_only=False):

        rocks_opts = Options()
        rocks_opts.create_if_missing = True

        if opts:
            if not isinstance(opts, dict):
                raise TypeError

            for key, value in opts.items():
                setattr(rocks_opts, key, value)

        self._db = RocksDB(f'{path}', rocks_opts, read_only=read_only)

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

    def scan(self, prefix=None, reversed=False):
        iterator = self._db.iterkeys()

        if prefix is None:
            iterator.seek_to_first()
        else:
            prefix_bytes = utils.str_to_bytes(prefix)
            iterator.seek(prefix_bytes)

        if reversed:
            iterator = reversed(iterator)

        for key_bytes in iterator:
            key = utils.bytes_to_str(key_bytes)
            if prefix is not None and key[:len(prefix)] != prefix:
                return

            value_bytes = self._db.get(key_bytes)
            value = utils.to_object(value_bytes)
            yield key, value

    def close(self):
        self._db.close()