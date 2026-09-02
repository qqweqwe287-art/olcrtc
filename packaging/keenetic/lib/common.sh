#!/bin/sh
# ai-generated: shared POSIX shell helpers for the Keenetic Entware package.
# shellcheck disable=SC2034 # shared constants are consumed by sourcing scripts.

OLCRTC_PREFIX=${OLCRTC_PREFIX:-/opt}
OLCRTC_NAME=olcrtc-keenetic
OLCRTC_BIN="$OLCRTC_PREFIX/bin/olcrtc"
OLCRTC_LIB="$OLCRTC_PREFIX/lib/$OLCRTC_NAME"
OLCRTC_ETC="$OLCRTC_PREFIX/etc/$OLCRTC_NAME"
OLCRTC_CONFIG="$OLCRTC_ETC/client.yaml"
OLCRTC_PROFILE="$OLCRTC_ETC/profile.json"
OLCRTC_LOG="$OLCRTC_PREFIX/var/log/$OLCRTC_NAME"
OLCRTC_RUN="$OLCRTC_PREFIX/var/run/$OLCRTC_NAME"
OLCRTC_STATE="$OLCRTC_PREFIX/var/lib/$OLCRTC_NAME"
OLCRTC_INIT="$OLCRTC_PREFIX/etc/init.d/S96olcrtc-native"
OLCRTC_ENABLED="$OLCRTC_ETC/native.enabled"
OLCRTC_LEGACY_INIT="$OLCRTC_PREFIX/etc/init.d/S98olcrtc-client"
OLCRTC_LEGACY_DISABLED="$OLCRTC_PREFIX/etc/init.d/S98olcrtc-client.olcrtc-disabled"
OLCRTC_LEGACY_ETC="$OLCRTC_PREFIX/etc/olcrtc-client"
OLCRTC_LEGACY_BIN="$OLCRTC_PREFIX/bin/olcrtc-client"
OLCRTC_RUNNER_PID="$OLCRTC_RUN/supervisor.pid"
OLCRTC_CHILD_PID="$OLCRTC_RUN/client.pid"
OLCRTC_BLOCKED="$OLCRTC_RUN/blocked.reason"
OLCRTC_CLIENT_LOG="$OLCRTC_LOG/client.log"
OLCRTC_RELEASE="$OLCRTC_ETC/release.tsv"
OLCRTC_MANIFEST_URL_FILE="$OLCRTC_ETC/manifest.url"
OLCRTC_RUN_USER=${OLCRTC_RUN_USER:-nobody}
OLCRTC_REPOSITORY=${OLCRTC_REPOSITORY:-qqweqwe287-art/olcrtc}
OLCRTC_WEB_INIT="$OLCRTC_PREFIX/etc/init.d/S97olcrtc-web"
OLCRTC_WEB_CONFIG="$OLCRTC_ETC/web.json"
OLCRTC_WEB_PID="$OLCRTC_RUN/web.pid"
OLCRTC_WEB_LOG="$OLCRTC_LOG/web.log"
OLCRTC_CONFIG_BACKUP="$OLCRTC_STATE/config.previous"

# ai-generated: print a stable operator-facing status line.
olc_log() {
    printf '%s\n' "[olcRTC] $*"
}

# ai-generated: stop the current command with a concise error.
olc_die() {
    printf '%s\n' "[olcRTC] ERROR: $*" >&2
    exit 1
}

# ai-generated: require a command before destructive or network work starts.
olc_need_command() {
    command -v "$1" >/dev/null 2>&1 || olc_die "required command not found: $1"
}

# ai-generated: require the effective root account on the router.
olc_require_root() {
    [ "$(id -u)" = "0" ] || olc_die "run this command as root"
}

# ai-generated: create package paths without changing network configuration.
olc_make_directories() {
    mkdir -p "$OLCRTC_LIB" "$OLCRTC_ETC" "$OLCRTC_LOG" "$OLCRTC_RUN" "$OLCRTC_STATE"
    chmod 750 "$OLCRTC_ETC"
    chmod 700 "$OLCRTC_LOG" "$OLCRTC_RUN" "$OLCRTC_STATE"
}

# ai-generated: apply least-privilege ownership while keeping secrets root-owned.
olc_secure_permissions() {
    run_group=$(id -g "$OLCRTC_RUN_USER" 2>/dev/null || printf '%s' "$OLCRTC_RUN_USER")
    chown root:"$run_group" "$OLCRTC_ETC" 2>/dev/null || true
    chown "$OLCRTC_RUN_USER":"$run_group" "$OLCRTC_LOG" "$OLCRTC_RUN" "$OLCRTC_STATE" 2>/dev/null || true
    chmod 750 "$OLCRTC_ETC"
    chmod 700 "$OLCRTC_LOG" "$OLCRTC_RUN" "$OLCRTC_STATE"
    chown root:"$run_group" "$OLCRTC_CONFIG" "$OLCRTC_PROFILE" "$OLCRTC_ETC"/secret-*.key 2>/dev/null || true
    chmod 640 "$OLCRTC_CONFIG" "$OLCRTC_PROFILE" "$OLCRTC_ETC"/secret-*.key 2>/dev/null || true
    chown root:root "$OLCRTC_WEB_CONFIG" 2>/dev/null || true
    chmod 600 "$OLCRTC_WEB_CONFIG" 2>/dev/null || true
}

# ai-generated: calculate a portable SHA-256 digest.
olc_sha256() {
    sha256sum "$1" | awk '{print $1}'
}

# ai-generated: calculate a byte count without parsing localized ls output.
olc_size() {
    wc -c <"$1" | tr -d '[:space:]'
}

# ai-generated: verify a PID file and optional process command marker.
olc_pid_alive() {
    pid_file=$1
    marker=${2:-}
    [ -s "$pid_file" ] || return 1
    pid=$(sed -n '1p' "$pid_file" 2>/dev/null)
    case "$pid" in
        ''|*[!0-9]*) return 1 ;;
    esac
    kill -0 "$pid" 2>/dev/null || return 1
    if [ -n "$marker" ] && [ -r "/proc/$pid/cmdline" ]; then
        tr '\000' ' ' <"/proc/$pid/cmdline" | grep -F "$marker" >/dev/null 2>&1 || return 1
    fi
    return 0
}

# ai-generated: securely create a temporary working directory under Entware.
olc_tmpdir() {
    base="$OLCRTC_PREFIX/tmp"
    mkdir -p "$base"
    if command -v mktemp >/dev/null 2>&1; then
        mktemp -d "$base/olcrtc.XXXXXX"
        return
    fi
    candidate="$base/olcrtc.$$"
    (umask 077 && mkdir "$candidate") || return 1
    printf '%s\n' "$candidate"
}

# ai-generated: download one HTTPS resource with bounded retries.
olc_download() {
    url=$1
    output=$2
    case "$url" in
        https://*) ;;
        *) olc_die "refusing non-HTTPS download URL" ;;
    esac
    curl -fL --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 600 \
        --retry 3 --retry-delay 2 -o "$output" "$url" \
        || olc_die "download failed: $url"
}

# ai-generated: verify size and checksum before an asset can be installed.
olc_verify_asset() {
    file=$1
    expected_size=$2
    expected_sha=$3
    actual_size=$(olc_size "$file")
    [ "$actual_size" = "$expected_size" ] \
        || olc_die "asset size mismatch: expected $expected_size, got $actual_size"
    actual_sha=$(olc_sha256 "$file")
    [ "$actual_sha" = "$expected_sha" ] \
        || olc_die "asset SHA-256 mismatch"
}

# ai-generated: build a GitHub release asset URL only from validated components.
olc_asset_url() {
    repository=$1
    version=$2
    filename=$3
    printf 'https://github.com/%s/releases/download/%s/%s\n' "$repository" "$version" "$filename"
}

# ai-generated: read one scalar through the strict non-executing manifest parser.
olc_manifest_get() {
    manifest=$1
    key=$2
    python3 "$OLCRTC_LIB/lib/manifest.py" "$manifest" get "$key"
}

# ai-generated: read one asset through the strict non-executing manifest parser.
olc_manifest_asset() {
    manifest=$1
    kind=$2
    system=$3
    arch=$4
    python3 "$OLCRTC_LIB/lib/manifest.py" "$manifest" asset "$kind" "$system" "$arch"
}

# ai-generated: rotate bounded local logs before another supervisor run.
olc_rotate_log() {
    file=$1
    limit=${2:-2097152}
    [ -f "$file" ] || return 0
    size=$(olc_size "$file")
    [ "$size" -le "$limit" ] && return 0
    rm -f "$file.2"
    [ ! -f "$file.1" ] || mv "$file.1" "$file.2"
    mv "$file" "$file.1"
}

