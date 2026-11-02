#!/usr/bin/env python
# -*- coding: utf-8 -*-

import io
import pickle
import pickletools
from collections import OrderedDict

import msgpack


_SAFE_PICKLE_GLOBALS = {
    ('collections', 'OrderedDict'): OrderedDict,
}


class _RestrictedUnpickler(pickle.Unpickler):
    """Read legacy primitive values without permitting arbitrary imports."""

    def find_class(self, module, name):
        allowed = _SAFE_PICKLE_GLOBALS.get((module, name))
        if allowed is None:
            raise pickle.UnpicklingError(
                f'forbidden legacy pickle global: {module}.{name}'
            )
        return allowed


def _validate_safe_flag(safe):
    if not isinstance(safe, bool):
        raise TypeError('safe must be a boolean')


def _validate_serializable(value, seen=None, map_key=False):
    if map_key and not isinstance(value, (str, bytes)):
        raise TypeError('safe map keys must be strings or bytes')
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return
    if seen is None:
        seen = set()
    value_id = id(value)
    if value_id in seen:
        raise TypeError('cyclic values are not supported')
    seen.add(value_id)
    try:
        if isinstance(value, (list, tuple)):
            for item in value:
                _validate_serializable(item, seen)
            return
        if isinstance(value, (dict, OrderedDict)):
            for key, item in value.items():
                _validate_serializable(key, seen, map_key=True)
                _validate_serializable(item, seen)
            return
    finally:
        seen.remove(value_id)
    raise TypeError(
        f'unsupported RocksDB value type: {type(value).__name__}'
    )


def pack(value, safe=False) -> bytes:
    _validate_safe_flag(safe)
    if safe:
        _validate_serializable(value)
        # Safe mode never falls back to Pickle for newly written values.  A
        # restricted Pickle reader exists only to migrate primitive records
        # produced by older Easyrocks versions.
        return msgpack.packb(value, use_bin_type=True)
    try:
        return msgpack.packb(value, use_bin_type=True)
    except TypeError:
        return pickle.dumps(value, protocol=5)


def unpack(value: bytes, safe=False):
    _validate_safe_flag(safe)
    if not isinstance(value, bytes):
        raise TypeError('value must be bytes')
    try:
        # Safe mode keeps msgpack's map-key hardening enabled.  Legacy mode
        # accepts the broader historical MessagePack key contract, but must
        # only be used with trusted databases.
        return msgpack.unpackb(
            value,
            raw=False,
            strict_map_key=safe,
        )
    except Exception:
        if not safe:
            return pickle.loads(value)
        try:
            # Extension-cache hits can bypass Unpickler.find_class.
            for opcode, _, _ in pickletools.genops(value):
                if opcode.name in ('EXT1', 'EXT2', 'EXT4'):
                    raise pickle.UnpicklingError(
                        'pickle extensions are forbidden')
            source = io.BytesIO(value)
            result = _RestrictedUnpickler(source).load()
            if source.read(1):
                raise pickle.UnpicklingError(
                    'trailing data after legacy pickle'
                )
            _validate_serializable(result)
            return result
        except Exception as pickle_error:
            raise ValueError(
                'stored value is neither valid MessagePack nor a safe '
                'legacy pickle'
            ) from pickle_error


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
