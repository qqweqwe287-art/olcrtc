#!/bin/sh
# ai-generated: explicit binary rollback with health verification and reverse rollback.
set -eu

# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

olc_require_root
[ -x "$OLCRTC_BIN.previous" ] || olc_die "previous binary is not available"
was_enabled=no
[ ! -f "$OLCRTC_ENABLED" ] || was_enabled=yes
"$OLCRTC_INIT" stop 2>/dev/null || true
mv "$OLCRTC_BIN" "$OLCRTC_BIN.rollback-new"
if ! mv "$OLCRTC_BIN.previous" "$OLCRTC_BIN"; then
    mv "$OLCRTC_BIN.rollback-new" "$OLCRTC_BIN"
    olc_die "failed to activate previous binary"
fi
mv "$OLCRTC_BIN.rollback-new" "$OLCRTC_BIN.previous"
if [ "$was_enabled" = yes ]; then
    if ! "$OLCRTC_INIT" start; then
        "$OLCRTC_INIT" stop 2>/dev/null || true
        mv "$OLCRTC_BIN" "$OLCRTC_BIN.rollback-failed"
        mv "$OLCRTC_BIN.previous" "$OLCRTC_BIN"
        mv "$OLCRTC_BIN.rollback-failed" "$OLCRTC_BIN.previous"
        "$OLCRTC_INIT" start 2>/dev/null || true
        olc_die "previous binary failed to start; newer binary was restored"
    fi
fi
olc_log "binary rollback complete; the replaced binary remains available for reverse rollback"
