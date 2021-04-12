#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pickle
import msgpack


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


def str_to_bytes(value: str) -> bytes:
    return bytes(value, 'utf-8')


def bytes_to_str(value: bytes) -> str:
    if value is not None:
        return value.decode('utf-8')


def _big_endian_to_int(value: bytes) -> int:
    return int.from_bytes(value, "big")


def _int_to_big_endian(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, 'big')


def int_to_bytes(value: int):
    return _int_to_big_endian(value)


def bytes_to_int(value: bytes):
    return _big_endian_to_int(value)


def str_to_padded_bytes(value: str, length: int) -> bytes:
    str_bytes = str_to_bytes(value)
    return str_bytes.rjust(length, b'\x00')


def int_to_padded_bytes(value: int, lenght: int) -> bytes:
    int_bytes = int_to_bytes(value)
    return int_bytes.rjust(lenght, b'\x00')
