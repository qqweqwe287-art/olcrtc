#!/bin/sh
# ai-generated: safe URI import wrapper that never places the secret in argv by default.
set -eu

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

uri_file=
settings_file=
temporary_uri=
read_stdin=no
read_settings_stdin=no
show_profile=no
restart_client=no
input_hidden=no

# ai-generated: remove a temporary URI file on every exit path.
cleanup_import() {
    if [ "$input_hidden" = yes ] && [ -r /dev/tty ]; then
        stty echo </dev/tty 2>/dev/null || true
    fi
    [ -z "$temporary_uri" ] || rm -f "$temporary_uri"
}

trap cleanup_import EXIT INT TERM

while [ "$#" -gt 0 ]; do
    case "$1" in
        --uri-file)
            [ "$#" -ge 2 ] || olc_die "--uri-file requires a path"
            uri_file=$2
            shift 2
            ;;
        --stdin) read_stdin=yes; shift ;;
        --settings-file)
            [ "$#" -ge 2 ] || olc_die "--settings-file requires a path"
            settings_file=$2
            shift 2
            ;;
        --settings-stdin) read_settings_stdin=yes; shift ;;
        --show) show_profile=yes; shift ;;
        --restart) restart_client=yes; shift ;;
        *) olc_die "unknown option: $1" ;;
    esac
done

olc_require_root
olc_need_command python3

selected=0
[ -z "$uri_file" ] || selected=$((selected + 1))
[ "$read_stdin" = no ] || selected=$((selected + 1))
[ -z "$settings_file" ] || selected=$((selected + 1))
[ "$read_settings_stdin" = no ] || selected=$((selected + 1))
[ "$show_profile" = no ] || selected=$((selected + 1))
[ "$selected" -le 1 ] || olc_die "choose only one input mode"

if [ "$show_profile" = yes ]; then
    python3 "$OLCRTC_LIB/lib/uri_import.py" --show --config "$OLCRTC_CONFIG" --profile "$OLCRTC_PROFILE"
    exit $?
fi

if [ "$read_stdin" = yes ] || [ "$read_settings_stdin" = yes ]; then
    [ -z "$uri_file" ] || olc_die "--stdin and --uri-file cannot be combined"
    temporary_uri="$OLCRTC_RUN/import-uri.$$"
    umask 077
    if [ "$read_stdin" = yes ]; then
        IFS= read -r input_value || olc_die "failed to read URI from stdin"
        [ "${#input_value}" -le 8192 ] || olc_die "URI is too long"
        printf '%s\n' "$input_value" >"$temporary_uri"
        uri_file=$temporary_uri
    else
        input_value=$(dd bs=65536 count=1 2>/dev/null) || olc_die "failed to read settings from stdin"
        [ "${#input_value}" -le 32768 ] || olc_die "settings input is too long"
        printf '%s\n' "$input_value" >"$temporary_uri"
        settings_file=$temporary_uri
    fi
    unset input_value
elif [ -z "$uri_file" ] && [ -z "$settings_file" ]; then
    [ -r /dev/tty ] || olc_die "use --uri-file when no interactive terminal is available"
    temporary_uri="$OLCRTC_RUN/import-uri.$$"
    umask 077
    printf '%s\n' "Paste the raw olcrtc:// URI below. Input is hidden; press Enter after pasting." >/dev/tty
    printf '%s' "Spec URI: " >/dev/tty
    stty -echo </dev/tty 2>/dev/null || true
    input_hidden=yes
    IFS= read -r uri_value </dev/tty || {
        stty echo </dev/tty 2>/dev/null || true
        input_hidden=no
        olc_die "failed to read URI"
    }
    stty echo </dev/tty 2>/dev/null || true
    input_hidden=no
    printf '\n' >/dev/tty
    printf '%s\n' "$uri_value" >"$temporary_uri"
    unset uri_value
    uri_file=$temporary_uri
fi

input_file=$uri_file
[ -z "$settings_file" ] || input_file=$settings_file
if [ ! -f "$input_file" ] || [ ! -r "$input_file" ]; then
    olc_die "input file is not readable"
fi

rm -rf "$OLCRTC_CONFIG_BACKUP.tmp"
mkdir -p "$OLCRTC_CONFIG_BACKUP.tmp"
chmod 700 "$OLCRTC_CONFIG_BACKUP.tmp"
for old_file in "$OLCRTC_CONFIG" "$OLCRTC_PROFILE" "$OLCRTC_ETC"/secret-*.key; do
    [ -f "$old_file" ] || continue
    cp "$old_file" "$OLCRTC_CONFIG_BACKUP.tmp/"
done
if [ -n "$settings_file" ]; then
    set -- --settings-file "$settings_file"
else
    set -- --uri-file "$uri_file"
fi
if ! python3 "$OLCRTC_LIB/lib/uri_import.py" "$@" --config "$OLCRTC_CONFIG" --profile "$OLCRTC_PROFILE"; then
    rm -rf "$OLCRTC_CONFIG_BACKUP.tmp"
    olc_die "configuration was not changed"
fi
rm -rf "$OLCRTC_CONFIG_BACKUP"
mv "$OLCRTC_CONFIG_BACKUP.tmp" "$OLCRTC_CONFIG_BACKUP"
olc_secure_permissions
if [ "$restart_client" = yes ]; then
    if ! "$OLCRTC_INIT" restart || ! "$OLCRTC_INIT" status >/dev/null 2>&1; then
        "$OLCRTC_INIT" stop 2>/dev/null || true
        rm -f "$OLCRTC_CONFIG" "$OLCRTC_PROFILE" "$OLCRTC_ETC"/secret-*.key
        for old_file in "$OLCRTC_CONFIG_BACKUP"/*; do
            [ -f "$old_file" ] || continue
            cp "$old_file" "$OLCRTC_ETC/"
        done
        olc_secure_permissions
        [ ! -s "$OLCRTC_CONFIG" ] || "$OLCRTC_INIT" start 2>/dev/null || true
        olc_die "new configuration failed to start; previous configuration was restored"
    fi
    olc_log "configuration applied and client restarted"
else
    olc_log "configuration saved; restart the client to apply it"
fi
