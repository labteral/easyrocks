#!/usr/bin/env python
# -*- coding: utf-8 -*-

import easyrocks
from easyrocks import RocksDB
from easyrocks.utils import str_to_bytes

print(f'easyrocks v{easyrocks.__version__}')
db = RocksDB(path='/tmp/rocksdb')
backup_path = '/tmp/rocksdb-backup'

# RELOAD AS READ-ONLY
db.reload(read_only=True)
try:
    db.put("key1", "value1")
    put = True
except Exception:
    put = False
assert not put

# RELOAD AS WRITABLE
db.reload()

# PUT
for i in range(6):
    key = str_to_bytes(f'key{i + 1}')
    db.put(key, f'value{i + 1}')
    assert db.get(key) == f'value{i + 1}'
    assert db.exists(key)

# CREATE TWO BACKUPS
db.backup(path=backup_path)

# BACKUP INFO
backup_info = db.backup_info(backup_path)
number_of_backup = len(backup_info)

# RESTORE FIRST BACKUP
db.restore_backup(backup_path, backup_info[0]['backup_id'])

# RESTORE LATEST BACKUP
db.restore_backup(backup_path)

# DELETE LATEST BACKUP
db.delete_backup(backup_path, backup_info[-1]['backup_id'])
backup_info = db.backup_info(backup_path)
assert number_of_backup - 1 == len(backup_info)

# DELETE
key = str_to_bytes('key6')
db.delete(key)
assert not db.get(key)
assert not db.exists(key)

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
start_key = str_to_bytes('key2')
for _, value in db.scan(start_key=start_key):
    assert value == f'value{index}'
    index += 1
assert index == 6

# START & STOP KEYS
index = 2
start_key = str_to_bytes('key2')
stop_key = str_to_bytes('key3')
for _, value in db.scan(start_key=start_key, stop_key=stop_key):
    assert value == f'value{index}'
    index += 1
assert index == 4

# START & STOP KEYS ARE THE SAME
start_key = str_to_bytes('key3')
stop_key = str_to_bytes('key3')
for _, value in db.scan(start_key=start_key, stop_key=stop_key):
    assert value == 'value3'

# START & STOP KEYS DO NOT EXIST
index = 1
start_key = str_to_bytes('key0')
stop_key = str_to_bytes('key9')
for _, value in db.scan(start_key=start_key, stop_key=stop_key):
    assert value == f'value{index}'
    index += 1
assert index == 6

print('OK!')
