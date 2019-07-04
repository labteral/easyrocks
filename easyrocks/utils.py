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


def get_padded_int(integer):
    integer_string = str(integer)
    zeros = 16 - len(integer_string)
    if zeros < 0:
        raise ValueError
    integer_string = f"{zeros * '0'}{integer_string}"
    return integer_string


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