#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
source "$SCRIPT_DIR/env.sh"

docker build \
    --pull \
    --file "$SCRIPT_DIR/Dockerfile" \
    --tag "labteral/easyrocks:$VERSION" \
    --build-arg "EASYROCKS_VERSION=$VERSION" \
    "$ROOT_DIR"
docker tag "labteral/easyrocks:$VERSION" labteral/easyrocks:latest
