#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pickle


def to_bytes(value):
    return pickle.dumps(value, protocol=4)


def to_object(bytes_value):
    return pickle.loads(bytes_value)


def str_to_bytes(string):
    if string == None:
        return
    return bytes(string, 'utf-8')


def bytes_to_str(bytes_string):
    if bytes_string == None:
        return
    return bytes_string.decode('utf-8')


def get_padded_int(integer, size=32, left=True, right=False):
    integer_string = str(integer)
    return get_padded_str(integer_string, size, left, right)


def get_padded_str(key, size=64, left=True, right=False):
    if (left and right) or (not left and not right):
        raise ValueError

    zeros = size - len(key)
    if zeros < 0:
        raise ValueError
    if left:
        new_key = f"{zeros * '0'}{key}"
    else:
        new_key = f"{key}{zeros * '0'}"
    return new_key


def int_to_bytes(integer):
    return str_to_bytes(get_padded_int(integer))


def _get_key_bytes(key):
    if isinstance(key, int):
        key_bytes = int_to_bytes(key)
    elif isinstance(key, str):
        key_bytes = str_to_bytes(key)
    else:
        raise TypeError
    return key_bytes