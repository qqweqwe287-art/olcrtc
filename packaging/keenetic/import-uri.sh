#!/bin/sh
# ai-generated: safe URI import wrapper that never places the secret in argv by default.
set -eu

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

uri_file=
temporary_uri=
read_stdin=no
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
        *) olc_die "unknown option: $1" ;;
    esac
done

olc_require_root
olc_need_command python3

if [ "$read_stdin" = yes ]; then
    [ -z "$uri_file" ] || olc_die "--stdin and --uri-file cannot be combined"
    temporary_uri="$OLCRTC_RUN/import-uri.$$"
    umask 077
    IFS= read -r uri_value || olc_die "failed to read URI from stdin"
    [ "${#uri_value}" -le 8192 ] || olc_die "URI is too long"
    printf '%s\n' "$uri_value" >"$temporary_uri"
    unset uri_value
    uri_file=$temporary_uri
elif [ -z "$uri_file" ]; then
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

if [ ! -f "$uri_file" ] || [ ! -r "$uri_file" ]; then
    olc_die "URI file is not readable"
fi
python3 "$OLCRTC_LIB/lib/uri_import.py" --uri-file "$uri_file" --config "$OLCRTC_CONFIG" \
    || olc_die "configuration was not changed"
olc_secure_permissions
olc_log "URI imported; restart the client to apply it"
