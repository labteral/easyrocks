#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rocksdb
from . import utils
from rocksdb import DB as RocksDB, Options, WriteBatch


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class DB(metaclass=Singleton):
    def __init__(self, path='./rocksdb', opts=None):

        rocks_opts = Options()
        rocks_opts.create_if_missing = True

        if opts:
            if not isinstance(opts, dict):
                raise TypeError

            for key, value in opts.items():
                setattr(rocks_opts, key, value)

        self._db = RocksDB(f'{path}', rocks_opts)

    def put(self, key, value, write_batch=None):
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

    def delete(self, key):
        key_bytes = utils.str_to_bytes(key)
        self._db.delete(key_bytes, sync=True)

    def scan(self, prefix=None, reversed=False):
        iterator = self._db.iterkeys()

        if prefix is not None:
            prefix = utils.str_to_bytes(prefix)
            iterator.seek(prefix)
        else:
            iterator.seek_to_first()

        if reversed:
            iterator = reversed(iterator)

        for key_bytes in iterator:
            try:
                key = utils.bytes_to_str(key_bytes)
            except IndexError:
                return

            value_bytes = self._db.get(key_bytes)
            value = utils.to_object(value_bytes)
            yield key, value