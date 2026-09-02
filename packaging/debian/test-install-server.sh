#!/bin/sh
# ai-generated: regression checks for installer paths that do not need root or network.
set -eu

ROOT=$(
    unset CDPATH
    cd -- "$(dirname -- "$0")/../.."
    pwd
)
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT HUP INT TERM

awk '
    /^install_config\(\) \{/ { copying = 1 }
    copying { print }
    copying && /^}/ { exit }
' "$ROOT/packaging/debian/install-server.sh" >"$TMP_ROOT/install-config-function.sh"

awk '
    /^prepare_v011_migration\(\) \{/ { copying = 1 }
    copying { print }
    copying && /^}/ { exit }
' "$ROOT/packaging/debian/install-server.sh" >>"$TMP_ROOT/install-config-function.sh"

cat >>"$TMP_ROOT/install-config-function.sh" <<'EOF'
mkdir() { :; }
chown() { :; }
chmod() { :; }
install() { :; }
die() {
    printf '%s\n' "unexpected die: $*" >&2
    return 99
}

CONFIG_DIR=/etc/olcrtc-native
BUNDLE_DIR=/tmp/bundle
CONFIG_SOURCE=
INSTANCE=main
REPLACE_CONFIG=0

install_config
MIGRATE_V011=0
prepare_v011_migration
EOF

sh "$TMP_ROOT/install-config-function.sh"
printf '%s\n' 'install-server regression tests: ok'
