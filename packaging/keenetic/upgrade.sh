#!/bin/sh
# ai-generated: verified atomic core updater with immediate-start rollback.
set -eu

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

manifest_file=
manifest_url=
start_after=yes
temporary_dir=

# ai-generated: remove downloaded update material on all exit paths.
cleanup_upgrade() {
    [ -z "$temporary_dir" ] || rm -rf "$temporary_dir"
}

trap cleanup_upgrade EXIT INT TERM

while [ "$#" -gt 0 ]; do
    case "$1" in
        --manifest-file)
            [ "$#" -ge 2 ] || olc_die "--manifest-file requires a path"
            manifest_file=$2
            shift 2
            ;;
        --manifest-url)
            [ "$#" -ge 2 ] || olc_die "--manifest-url requires a URL"
            manifest_url=$2
            shift 2
            ;;
        --no-start)
            start_after=no
            shift
            ;;
        *) olc_die "unknown option: $1" ;;
    esac
done

olc_require_root
olc_need_command curl
olc_need_command python3
olc_need_command sha256sum
olc_make_directories
temporary_dir=$(olc_tmpdir) || olc_die "failed to create a temporary directory"

if [ -z "$manifest_file" ]; then
    if [ -z "$manifest_url" ] && [ -s "$OLCRTC_MANIFEST_URL_FILE" ]; then
        manifest_url=$(sed -n '1p' "$OLCRTC_MANIFEST_URL_FILE")
    fi
    [ -n "$manifest_url" ] || olc_die "no manifest URL is configured"
    manifest_file="$temporary_dir/manifest.tsv"
    olc_download "$manifest_url" "$manifest_file"
fi

python3 "$OLCRTC_LIB/lib/manifest.py" "$manifest_file" validate \
    || olc_die "release manifest validation failed"
repository=$(olc_manifest_get "$manifest_file" source_repository)
[ "$repository" = "$OLCRTC_REPOSITORY" ] \
    || olc_die "manifest repository does not match $OLCRTC_REPOSITORY"
version=$(olc_manifest_get "$manifest_file" version)
asset_fields=$(olc_manifest_asset "$manifest_file" core linux arm64) \
    || olc_die "ARM64 core asset is missing from the manifest"
old_ifs=$IFS
tab=$(printf '\t')
IFS=$tab
# shellcheck disable=SC2086 # validated TSV fields require intentional splitting.
set -- $asset_fields
IFS=$old_ifs
[ "$#" -eq 3 ] || olc_die "invalid ARM64 asset row"
asset_name=$1
asset_size=$2
asset_sha=$3
asset_url=$(olc_asset_url "$repository" "$version" "$asset_name")
download="$temporary_dir/$asset_name"

olc_log "downloading olcRTC $version for linux/arm64"
olc_download "$asset_url" "$download"
olc_verify_asset "$download" "$asset_size" "$asset_sha"
python3 "$OLCRTC_LIB/lib/manifest.py" "$manifest_file" get source_commit >/dev/null
python3 - "$download" <<'PY'
# ai-generated: reject a checksum-valid asset for the wrong ELF architecture.
import pathlib
import struct
import sys

path = pathlib.Path(sys.argv[1])
header = path.read_bytes()[:20]
if len(header) < 20 or header[:4] != b"\x7fELF":
    raise SystemExit("asset is not an ELF executable")
if header[4] != 2 or header[5] != 1:
    raise SystemExit("asset must be little-endian ELF64")
machine = struct.unpack("<H", header[18:20])[0]
if machine != 183:
    raise SystemExit(f"asset machine is {machine}, expected AArch64 (183)")
PY
chmod 755 "$download"

if [ -x "$OLCRTC_INIT" ] && olc_pid_alive "$OLCRTC_RUNNER_PID" "run-client.sh"; then
    "$OLCRTC_INIT" stop
fi

backup="$OLCRTC_BIN.previous"
had_binary=no
if [ -f "$OLCRTC_BIN" ]; then
    had_binary=yes
    rm -f "$backup"
    mv "$OLCRTC_BIN" "$backup"
fi
if ! mv "$download" "$OLCRTC_BIN"; then
    [ "$had_binary" = no ] || mv "$backup" "$OLCRTC_BIN"
    olc_die "failed to install the verified binary"
fi
chmod 755 "$OLCRTC_BIN"
had_release=no
if [ -f "$OLCRTC_RELEASE" ]; then
    cp "$OLCRTC_RELEASE" "$temporary_dir/release.previous"
    had_release=yes
fi
had_manifest_url=no
if [ -f "$OLCRTC_MANIFEST_URL_FILE" ]; then
    cp "$OLCRTC_MANIFEST_URL_FILE" "$temporary_dir/manifest-url.previous"
    had_manifest_url=yes
fi
cp "$manifest_file" "$OLCRTC_RELEASE.tmp"
chmod 600 "$OLCRTC_RELEASE.tmp"
mv "$OLCRTC_RELEASE.tmp" "$OLCRTC_RELEASE"
if [ -n "$manifest_url" ]; then
    printf '%s\n' "$manifest_url" >"$OLCRTC_MANIFEST_URL_FILE.tmp"
    chmod 600 "$OLCRTC_MANIFEST_URL_FILE.tmp"
    mv "$OLCRTC_MANIFEST_URL_FILE.tmp" "$OLCRTC_MANIFEST_URL_FILE"
fi

if [ "$start_after" = yes ] && [ -s "$OLCRTC_CONFIG" ]; then
    if ! "$OLCRTC_INIT" start; then
        failed=yes
    else
        failed=no
        count=0
        healthy=no
        while [ "$count" -lt 30 ]; do
            [ ! -s "$OLCRTC_BLOCKED" ] || failed=yes
            olc_pid_alive "$OLCRTC_RUNNER_PID" "run-client.sh" || failed=yes
            [ "$failed" = no ] || break
            if olc_pid_alive "$OLCRTC_CHILD_PID" "$OLCRTC_BIN" \
                && "$OLCRTC_LIB/doctor.sh" --quick >/dev/null 2>&1; then
                healthy=yes
                break
            fi
            sleep 1
            count=$((count + 1))
        done
        [ "$healthy" = yes ] || failed=yes
    fi
    if [ "$failed" = yes ]; then
        "$OLCRTC_INIT" stop 2>/dev/null || true
        rm -f "$OLCRTC_BIN"
        if [ "$had_binary" = yes ]; then
            mv "$backup" "$OLCRTC_BIN"
        fi
        if [ "$had_release" = yes ]; then
            mv "$temporary_dir/release.previous" "$OLCRTC_RELEASE"
        else
            rm -f "$OLCRTC_RELEASE"
        fi
        if [ "$had_manifest_url" = yes ]; then
            mv "$temporary_dir/manifest-url.previous" "$OLCRTC_MANIFEST_URL_FILE"
        elif [ -n "$manifest_url" ]; then
            rm -f "$OLCRTC_MANIFEST_URL_FILE"
        fi
        [ "$had_binary" = no ] || "$OLCRTC_INIT" start 2>/dev/null || true
        olc_die "new binary failed immediately; previous binary was restored"
    fi
fi

olc_log "installed olcRTC $version; previous binary is kept at $backup"
