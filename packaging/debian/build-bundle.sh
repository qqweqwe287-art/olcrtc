#!/bin/sh
# ai-generated: reproducible Debian bundle builder used by release CI.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: build-bundle.sh OUTPUT_PATH" >&2
    exit 2
fi

output=$1
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
output_dir=$(dirname -- "$output")

for name in install-server.sh uninstall-server.sh olcrtc-server@.service server.example.yaml README.ru.md; do
    if [ ! -f "$script_dir/$name" ] || [ -L "$script_dir/$name" ]; then
        echo "required regular file is missing: $script_dir/$name" >&2
        exit 1
    fi
done

mkdir -p "$output_dir"

tar \
    --sort=name \
    --mtime='UTC 1970-01-01' \
    --owner=0 \
    --group=0 \
    --numeric-owner \
    -czf "$output" \
    -C "$script_dir" \
    README.ru.md \
    build-bundle.sh \
    install-server.sh \
    olcrtc-server@.service \
    server.example.yaml \
    uninstall-server.sh

echo "$output"
