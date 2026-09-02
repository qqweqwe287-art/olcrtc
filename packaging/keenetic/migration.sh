#!/bin/sh
# ai-generated: reversible cutover from the legacy proof-of-concept service.
set -eu

# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

# ai-generated: report whether a TCP listener currently owns the SOCKS port.
port_in_use() {
    python3 - <<'PY'
# ai-generated: connect only to the fixed loopback SOCKS port.
import socket

try:
    with socket.create_connection(("127.0.0.1", 8808), timeout=1):
        raise SystemExit(0)
except OSError:
    raise SystemExit(1)
PY
}

# ai-generated: wait for the native child and SOCKS listener to become healthy.
wait_native() {
    count=0
    while [ "$count" -lt 30 ]; do
        if olc_pid_alive "$OLCRTC_CHILD_PID" "$OLCRTC_BIN" && port_in_use; then
            return 0
        fi
        [ ! -s "$OLCRTC_BLOCKED" ] || return 1
        sleep 1
        count=$((count + 1))
    done
    return 1
}

# ai-generated: detect either active or previously disabled legacy init script.
legacy_path() {
    if [ -f "$OLCRTC_LEGACY_INIT" ]; then
        printf '%s\n' "$OLCRTC_LEGACY_INIT"
    elif [ -f "$OLCRTC_LEGACY_DISABLED" ]; then
        printf '%s\n' "$OLCRTC_LEGACY_DISABLED"
    fi
}

olc_require_root
olc_need_command python3

case "${1:-status}" in
    status)
        if [ -f "$OLCRTC_LEGACY_INIT" ]; then
            printf '%s\n' "legacy=installed"
        elif [ -f "$OLCRTC_LEGACY_DISABLED" ]; then
            printf '%s\n' "legacy=disabled-after-cutover"
        else
            printf '%s\n' "legacy=absent"
        fi
        [ -f "$OLCRTC_ENABLED" ] && printf '%s\n' "native=enabled" || printf '%s\n' "native=disabled"
        "$OLCRTC_INIT" status 2>/dev/null || true
        ;;
    enable)
        [ ! -f "$OLCRTC_LEGACY_INIT" ] \
            || olc_die "legacy service exists; use cutover instead of enable"
        [ -s "$OLCRTC_CONFIG" ] || olc_die "configure the native client first"
        : >"$OLCRTC_ENABLED"
        chmod 600 "$OLCRTC_ENABLED"
        "$OLCRTC_INIT" start
        wait_native || {
            "$OLCRTC_INIT" stop 2>/dev/null || true
            rm -f "$OLCRTC_ENABLED"
            olc_die "native client did not become healthy"
        }
        olc_log "native client enabled"
        ;;
    cutover)
        [ -f "$OLCRTC_LEGACY_INIT" ] || olc_die "active legacy service was not found"
        [ -s "$OLCRTC_CONFIG" ] || olc_die "configure the native client first"
        "$OLCRTC_INIT" stop 2>/dev/null || true
        "$OLCRTC_LEGACY_INIT" stop || olc_die "legacy service could not be stopped"
        count=0
        while port_in_use && [ "$count" -lt 10 ]; do
            sleep 1
            count=$((count + 1))
        done
        if port_in_use; then
            "$OLCRTC_LEGACY_INIT" start 2>/dev/null || true
            olc_die "port 8808 is still occupied; legacy service was restarted"
        fi
        : >"$OLCRTC_ENABLED"
        chmod 600 "$OLCRTC_ENABLED"
        if ! "$OLCRTC_INIT" start || ! wait_native; then
            "$OLCRTC_INIT" stop 2>/dev/null || true
            rm -f "$OLCRTC_ENABLED"
            "$OLCRTC_LEGACY_INIT" start 2>/dev/null || true
            olc_die "native client failed; legacy service was restored"
        fi
        if ! mv "$OLCRTC_LEGACY_INIT" "$OLCRTC_LEGACY_DISABLED"; then
            "$OLCRTC_INIT" stop 2>/dev/null || true
            rm -f "$OLCRTC_ENABLED"
            "$OLCRTC_LEGACY_INIT" start 2>/dev/null || true
            olc_die "could not disable legacy autostart; cutover was rolled back"
        fi
        olc_log "cutover complete; legacy init was preserved as $OLCRTC_LEGACY_DISABLED"
        ;;
    rollback)
        [ -f "$OLCRTC_LEGACY_DISABLED" ] || olc_die "disabled legacy service was not found"
        "$OLCRTC_INIT" stop 2>/dev/null || true
        rm -f "$OLCRTC_ENABLED"
        mv "$OLCRTC_LEGACY_DISABLED" "$OLCRTC_LEGACY_INIT" \
            || olc_die "could not restore legacy init script"
        "$OLCRTC_LEGACY_INIT" start || olc_die "legacy service was restored but failed to start"
        olc_log "legacy service restored; native client disabled"
        ;;
    purge-legacy)
        [ -f "$OLCRTC_LEGACY_DISABLED" ] \
            || olc_die "cut over successfully before deleting the legacy client"
        wait_native || olc_die "native client is not healthy; legacy files were preserved"
        stamp=$(date -u +%Y%m%dT%H%M%SZ)
        backup="$OLCRTC_STATE/legacy-backups/$stamp"
        mkdir -p "$backup"
        chmod 700 "$OLCRTC_STATE/legacy-backups" "$backup"
        for path in "$OLCRTC_LEGACY_DISABLED" "$OLCRTC_LEGACY_ETC" "$OLCRTC_LEGACY_BIN"; do
            if [ -e "$path" ] || [ -L "$path" ]; then
                cp -a "$path" "$backup/"
            fi
        done
        rm -f "$OLCRTC_LEGACY_DISABLED" "$OLCRTC_LEGACY_BIN"
        rm -rf "$OLCRTC_LEGACY_ETC"
        olc_log "legacy client removed; backup: $backup"
        ;;
    *)
        printf '%s\n' "usage: $0 {status|enable|cutover|rollback|purge-legacy}" >&2
        exit 2
        ;;
esac

