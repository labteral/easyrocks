#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pickle
import msgpack

NON_UINT_KEY_BYTES = 40
UINT_KEY_BYTES = 5
MAX_UINT = 2**(UINT_KEY_BYTES * 8) - 1


def pack(value) -> bytes:
    try:
        return msgpack.packb(value)
    except TypeError:
        return pickle.dumps(value, protocol=5)


def unpack(value: bytes):
    try:
        return msgpack.unpackb(value)
    except Exception:
        return pickle.loads(value)


def to_padded_bytes(value):
    if isinstance(value, str):
        return str_to_padded_bytes(value)
    if isinstance(value, int):
        return int_to_padded_bytes(value)
    if isinstance(value, bytes):
        if len(value) != NON_UINT_KEY_BYTES:
            raise ValueError(f'len(value) != {NON_UINT_KEY_BYTES}')
        return value
    raise TypeError


def bytes_to_str(bytes_string):
    if bytes_string is None:
        return
    return bytes_string.decode('utf-8')


def str_to_padded_bytes(value: str) -> bytes:
    str_bytes = bytes(value, 'utf-8')
    return str_bytes.rjust(NON_UINT_KEY_BYTES, b'\x00')


def int_to_big_endian(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")


def int_to_padded_bytes(value: int):
    if value > MAX_UINT:
        raise ValueError(f'{value} > {MAX_UINT}')
    int_bytes = int_to_big_endian(value)
    return int_bytes.rjust(UINT_KEY_BYTES, b'\x00')


def _get_key_bytes(key):
    if isinstance(key, bytes):
        return key

    if isinstance(key, int):
        return int_to_padded_bytes(key)

    if isinstance(key, str):
        return str_to_bytes(key)

    raise TypeError
