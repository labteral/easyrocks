#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)

VERSION=$(sed -n "s/^__version__ = '\([^']*\)'$/\1/p" \
    "$ROOT_DIR/easyrocks/_version.py")
if [[ -z "$VERSION" ]]; then
    echo 'Could not read easyrocks version.' >&2
    exit 1
fi
export VERSION
