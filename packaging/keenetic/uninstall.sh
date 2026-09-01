#!/bin/sh
# ai-generated: scoped uninstaller that preserves configuration unless explicitly purged.
set -eu

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

purge=no
while [ "$#" -gt 0 ]; do
    case "$1" in
        --purge) purge=yes; shift ;;
        *) olc_die "unknown option: $1" ;;
    esac
done

olc_require_root
[ ! -x "$OLCRTC_INIT" ] || "$OLCRTC_INIT" stop 2>/dev/null || true
[ ! -x "$OLCRTC_WEB_INIT" ] || "$OLCRTC_WEB_INIT" stop 2>/dev/null || true
rm -f "$OLCRTC_INIT" "$OLCRTC_WEB_INIT" "$OLCRTC_BIN" "$OLCRTC_BIN.previous"
rm -rf "$OLCRTC_LIB" "$OLCRTC_RUN" "$OLCRTC_LOG"
if [ "$purge" = yes ]; then
    rm -rf "$OLCRTC_ETC" "$OLCRTC_STATE"
    printf '%s\n' "[olcRTC] package, configuration and state removed"
else
    printf '%s\n' "[olcRTC] package removed; configuration preserved in $OLCRTC_ETC"
fi
printf '%s\n' "[olcRTC] Entware dependencies were not removed"
printf '%s\n' "[olcRTC] no TUN or routing rules were present in this package stage"
