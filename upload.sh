#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
VERSION=$(sed -n "s/^__version__ = '\([^']*\)'$/\1/p" \
    "$ROOT_DIR/easyrocks/_version.py")

if [[ -z "$VERSION" ]]; then
    echo 'Could not read easyrocks version.' >&2
    exit 1
fi
if [[ "${EASYROCKS_ALLOW_UPLOAD:-}" != "$VERSION" ]]; then
    echo "Refusing to upload. Set EASYROCKS_ALLOW_UPLOAD=$VERSION explicitly." >&2
    exit 64
fi

python3 -m twine check \
    "$ROOT_DIR/release/easyrocks-$VERSION-py3-none-any.whl" \
    "$ROOT_DIR/release/easyrocks-$VERSION.tar.gz"
python3 -m twine upload \
    "$ROOT_DIR/release/easyrocks-$VERSION-py3-none-any.whl" \
    "$ROOT_DIR/release/easyrocks-$VERSION.tar.gz"
