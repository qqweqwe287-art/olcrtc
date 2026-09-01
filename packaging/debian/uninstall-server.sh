#!/bin/sh
# ai-generated: scoped Debian server uninstaller with optional config purge.
set -eu

PURGE=0
LIB_DIR=/usr/local/lib/olcrtc
CONFIG_DIR=/etc/olcrtc
STATE_DIR=/var/lib/olcrtc
UNIT_PATH=/etc/systemd/system/olcrtc-server@.service
UNINSTALL_PATH=/usr/local/sbin/olcrtc-uninstall-server
BIN_LINK=/usr/local/bin/olcrtc

# ai-generated
usage() {
    cat <<'EOF'
Usage: uninstall-server.sh [--purge]

Without --purge, configs, state and the olcrtc service account are preserved.
With --purge, /etc/olcrtc, /var/lib/olcrtc and the service account are removed.
EOF
}

# ai-generated
die() {
    printf 'olcrtc-server-uninstaller: error: %s\n' "$*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --purge) PURGE=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
    shift
done

[ "$(id -u)" -eq 0 ] || die "run as root"

if command -v systemctl >/dev/null 2>&1; then
    units=$(systemctl list-unit-files --type=service --no-legend 'olcrtc-server@*.service' 2>/dev/null |
        awk '{print $1}')
    for unit in $units; do
        systemctl disable --now "$unit" >/dev/null 2>&1 || true
    done
fi

rm -f -- "$UNIT_PATH" "$BIN_LINK"
rm -rf -- "$LIB_DIR"

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
    systemctl reset-failed >/dev/null 2>&1 || true
fi

if [ "$PURGE" -eq 1 ]; then
    rm -rf -- "$CONFIG_DIR" "$STATE_DIR"
    if command -v userdel >/dev/null 2>&1 && getent passwd olcrtc >/dev/null 2>&1; then
        userdel olcrtc >/dev/null 2>&1 || true
    fi
    if command -v groupdel >/dev/null 2>&1 && getent group olcrtc >/dev/null 2>&1; then
        groupdel olcrtc >/dev/null 2>&1 || true
    fi
    printf '%s\n' 'olcrtc server, configs and state were removed'
else
    printf '%s\n' 'olcrtc server was removed; /etc/olcrtc and /var/lib/olcrtc were preserved'
fi

rm -f -- "$UNINSTALL_PATH"
