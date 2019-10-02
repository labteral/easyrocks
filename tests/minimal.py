#!/usr/bin/env python
# -*- coding: utf-8 -*-

import easyrocks
from easyrocks import DB

print(f'easyrocks v{easyrocks.__version__}')
db = DB(path='/tmp/rocksdb')

# PUT
for i in range(6):
    db.put(f'key{i + 1}', f'value{i + 1}')
    assert db.get(f'key{i + 1}') == f'value{i + 1}'
    assert db.exists(f'key{i + 1}')

# DELETE
db.delete('key6')
assert not db.get('key6')
assert not db.exists(f'key6')

# REGULAR SCAN
index = 1
for _, value in db.scan():
    assert value == f'value{index}'
    index += 1
assert index == 6

# REVERSED SCAN
index = 5
for _, value in db.scan(reversed_scan=True):
    assert value == f'value{index}'
    index -= 1
assert index == 0

# START KEY
index = 2
for _, value in db.scan(start_key='key2'):
    assert value == f'value{index}'
    index += 1
assert index == 6

# START & STOP KEYS
index = 2
for _, value in db.scan(start_key='key2', end_key='key3'):
    assert value == f'value{index}'
    index += 1
assert index == 4

# START & STOP KEYS ARE THE SAME
for _, value in db.scan(start_key='key3', end_key='key3'):
    assert value == 'value3'

print('OK!')