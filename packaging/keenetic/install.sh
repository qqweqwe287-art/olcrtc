#!/bin/sh
# ai-generated: idempotent installer for the verified Keenetic release bundle.
set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
manifest_file=
manifest_url=
uri_file=
no_start=no
web_password=
password_file=

# ai-generated: erase temporary web credentials on every installer exit path.
cleanup_install() {
    [ -z "$password_file" ] || rm -f "$password_file"
}

trap cleanup_install EXIT INT TERM

# ai-generated: print a pre-install failure before shared helpers are installed.
early_die() {
    printf '%s\n' "[olcRTC] ERROR: $*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --manifest-file)
            [ "$#" -ge 2 ] || early_die "--manifest-file requires a path"
            manifest_file=$2
            shift 2
            ;;
        --manifest-url)
            [ "$#" -ge 2 ] || early_die "--manifest-url requires a URL"
            manifest_url=$2
            shift 2
            ;;
        --uri-file)
            [ "$#" -ge 2 ] || early_die "--uri-file requires a path"
            uri_file=$2
            shift 2
            ;;
        --no-start) no_start=yes; shift ;;
        *) early_die "unknown option: $1" ;;
    esac
done

[ "$(id -u)" = "0" ] || early_die "run this command as root"
if [ ! -d /opt ] || [ ! -w /opt ]; then
    early_die "Entware /opt is missing or read-only"
fi
case "$(uname -m)" in
    aarch64|arm64) ;;
    *) early_die "this package requires ARM64, detected: $(uname -m)" ;;
esac
command -v opkg >/dev/null 2>&1 || early_die "Entware opkg was not found"

printf '%s\n' "[olcRTC] installing runtime dependencies"
opkg update || early_die "opkg update failed; check DNS, time and storage"
opkg install ca-bundle ca-certificates curl python3 || early_die "dependency installation failed"
command -v sha256sum >/dev/null 2>&1 || opkg install coreutils-sha256sum \
    || early_die "sha256sum is required"

mkdir -p /opt/lib/olcrtc-keenetic/lib /opt/etc/init.d
for file in upgrade.sh uninstall.sh doctor.sh import-uri.sh run-client.sh; do
    [ -f "$script_dir/$file" ] || early_die "release bundle is incomplete: $file"
    cp "$script_dir/$file" "/opt/lib/olcrtc-keenetic/$file.tmp"
    chmod 755 "/opt/lib/olcrtc-keenetic/$file.tmp"
    mv "/opt/lib/olcrtc-keenetic/$file.tmp" "/opt/lib/olcrtc-keenetic/$file"
done
for file in common.sh manifest.py uri_import.py; do
    [ -f "$script_dir/lib/$file" ] || early_die "release bundle is incomplete: lib/$file"
    cp "$script_dir/lib/$file" "/opt/lib/olcrtc-keenetic/lib/$file.tmp"
    chmod 755 "/opt/lib/olcrtc-keenetic/lib/$file.tmp"
    mv "/opt/lib/olcrtc-keenetic/lib/$file.tmp" "/opt/lib/olcrtc-keenetic/lib/$file"
done
[ -f "$script_dir/S98olcrtc-client" ] || early_die "release bundle is missing the client service"
cp "$script_dir/S98olcrtc-client" /opt/etc/init.d/S98olcrtc-client.tmp
chmod 755 /opt/etc/init.d/S98olcrtc-client.tmp
mv /opt/etc/init.d/S98olcrtc-client.tmp /opt/etc/init.d/S98olcrtc-client
[ -f "$script_dir/S97olcrtc-web" ] || early_die "release bundle is missing the web service"
cp "$script_dir/S97olcrtc-web" /opt/etc/init.d/S97olcrtc-web.tmp
chmod 755 /opt/etc/init.d/S97olcrtc-web.tmp
mv /opt/etc/init.d/S97olcrtc-web.tmp /opt/etc/init.d/S97olcrtc-web
[ -f "$script_dir/web-app.py" ] || early_die "release bundle is missing the web application"
cp "$script_dir/web-app.py" /opt/lib/olcrtc-keenetic/web-app.py.tmp
chmod 755 /opt/lib/olcrtc-keenetic/web-app.py.tmp
mv /opt/lib/olcrtc-keenetic/web-app.py.tmp /opt/lib/olcrtc-keenetic/web-app.py

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh
olc_make_directories

if [ ! -s "$OLCRTC_CONFIG" ]; then
    if [ -n "$uri_file" ]; then
        "$OLCRTC_LIB/import-uri.sh" --uri-file "$uri_file"
    else
        "$OLCRTC_LIB/import-uri.sh"
    fi
else
    olc_log "existing configuration was preserved"
fi

web_bind=127.0.0.1
if command -v ip >/dev/null 2>&1; then
    detected_bind=$(ip -4 addr show dev br0 2>/dev/null | awk '/inet / { sub("/.*", "", $2); print $2; exit }')
    [ -z "$detected_bind" ] || web_bind=$detected_bind
fi
if [ ! -s "$OLCRTC_WEB_CONFIG" ]; then
    web_password=$(python3 - <<'PY'
# ai-generated: create a one-time high-entropy web password without external tools.
import secrets

print(secrets.token_urlsafe(18))
PY
)
    password_file="$OLCRTC_RUN/web-password.$$"
    umask 077
    printf '%s\n' "$web_password" >"$password_file"
    set -- --config "$OLCRTC_WEB_CONFIG" init --bind "$web_bind" --password-file "$password_file"
    [ "$web_bind" = 127.0.0.1 ] || set -- "$@" --allow-lan
    python3 "$OLCRTC_LIB/web-app.py" "$@" || olc_die "web configuration failed"
    rm -f "$password_file"
    password_file=
else
    olc_log "existing web configuration was preserved"
    configured_bind=$(python3 - "$OLCRTC_WEB_CONFIG" <<'PY'
# ai-generated: read only the displayed bind address from root-owned JSON settings.
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle).get("bind", "127.0.0.1"))
PY
    ) || olc_die "existing web configuration is invalid"
    web_bind=$configured_bind
fi

olc_secure_permissions
set --
[ -z "$manifest_file" ] || set -- "$@" --manifest-file "$manifest_file"
[ -z "$manifest_url" ] || set -- "$@" --manifest-url "$manifest_url"
[ "$no_start" = no ] || set -- "$@" --no-start
[ "$#" -gt 0 ] || olc_die "installer requires --manifest-file or --manifest-url"
"$OLCRTC_LIB/upgrade.sh" "$@"

if [ "$no_start" = no ]; then
    "$OLCRTC_WEB_INIT" restart || olc_die "web service failed to start"
fi

olc_log "installation complete; TUN and router routes were not changed"
olc_log "status: $OLCRTC_INIT status"
olc_log "diagnostics: $OLCRTC_LIB/doctor.sh"
olc_log "updates: $OLCRTC_LIB/upgrade.sh"
olc_log "web UI: http://$web_bind:8091/ (LAN only; WAN binding is unsupported)"
if [ -n "$web_password" ]; then
    olc_log "web login: admin"
    olc_log "one-time web password: $web_password"
    olc_log "save this password now; it is not printed again"
fi
