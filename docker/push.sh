#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/env.sh"

if [[ "${EASYROCKS_ALLOW_PUSH:-}" != "$VERSION" ]]; then
    echo "Refusing to push. Set EASYROCKS_ALLOW_PUSH=$VERSION explicitly." >&2
    exit 64
fi

docker push "labteral/easyrocks:$VERSION"
docker push labteral/easyrocks:latest
