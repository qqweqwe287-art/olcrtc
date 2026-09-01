#!/bin/sh
# ai-generated: reproducible release bundle builder used by CI.
set -eu

[ "$#" -eq 1 ] || {
    printf '%s\n' "usage: $0 OUTPUT_PATH" >&2
    exit 2
}

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
temporary_dir=

# ai-generated: remove reproducible staging files after bundle creation.
cleanup_bundle() {
    [ -z "$temporary_dir" ] || rm -rf "$temporary_dir"
}

trap cleanup_bundle EXIT INT TERM
case "$1" in
    /*) output=$1 ;;
    *) output="$(pwd)/$1" ;;
esac
mkdir -p "$(dirname -- "$output")"

files='install.sh upgrade.sh uninstall.sh doctor.sh import-uri.sh run-client.sh S97olcrtc-web S98olcrtc-client client.example.yaml README.ru.md lib/common.sh lib/manifest.py lib/uri_import.py'
for file in $files; do
    [ -f "$script_dir/$file" ] || {
        printf '%s\n' "missing bundle input: $file" >&2
        exit 1
    }
done
[ -f "$script_dir/../../web/keenetic/app.py" ] || {
    printf '%s\n' "missing bundle input: web/keenetic/app.py" >&2
    exit 1
}

temporary_dir=$(mktemp -d) || exit 1
mkdir -p "$temporary_dir/lib"
for file in $files; do
    cp "$script_dir/$file" "$temporary_dir/$file"
done
cp "$script_dir/../../web/keenetic/app.py" "$temporary_dir/web-app.py"
# shellcheck disable=SC2086 # fixed internal file list requires intentional splitting.
set -- $files web-app.py
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C "$temporary_dir" -czf "$output" "$@"
