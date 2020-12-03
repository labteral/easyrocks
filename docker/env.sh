#!/bin/bash
export ROCKSDB_VERSION=6.10.2
export VERSION=$(cat ../easyrocks/__init__.py | grep __version__ | cut -f2 -d\')