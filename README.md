# easyrocks
A `python-rocksdb` wrapper for a more comfortable interaction with RocksDB.

> Keys must be strings. Values are serialized automatically with MessagePack if possible, otherwise with Pickle.

## Usage
```python
from easyrocks import RocksDB

db = RocksDB(path='./rocksdb', read_only=False)

key = b'key1'
db.put(key, 'one')
db.get(key)
db.exists(key)

for key, value in db.scan(prefix=None, start_key=None, stop_key=None, reversed_scan=False):
  print(key, value)
```

## Utils
There are some useful functions to transform a key to and from `bytes`:
```python
from easyrocks.utils import (
  str_to_bytes
  bytes_to_str
  int_to_bytes
  bytes_to_int
  str_to_padded_bytes
  int_to_padded_bytes
)
```
