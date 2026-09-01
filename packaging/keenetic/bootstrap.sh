#!/bin/sh
# ai-generated: one-line bootstrap that downloads and verifies the release bundle.
set -eu

repository=${OLCRTC_REPOSITORY:-qqweqwe287-art/olcrtc}
manifest_url=${OLCRTC_MANIFEST_URL:-}
uri_file=
no_start=no
temporary_dir=

# ai-generated: stop bootstrap with a concise error.
die() {
    printf '%s\n' "[olcRTC] ERROR: $*" >&2
    exit 1
}

# ai-generated: remove bootstrap downloads on every exit path.
cleanup() {
    [ -z "$temporary_dir" ] || rm -rf "$temporary_dir"
}

trap cleanup EXIT INT TERM

while [ "$#" -gt 0 ]; do
    case "$1" in
        --repository)
            [ "$#" -ge 2 ] || die "--repository requires owner/repository"
            repository=$2
            shift 2
            ;;
        --manifest-url)
            [ "$#" -ge 2 ] || die "--manifest-url requires a URL"
            manifest_url=$2
            shift 2
            ;;
        --uri-file)
            [ "$#" -ge 2 ] || die "--uri-file requires a path"
            uri_file=$2
            shift 2
            ;;
        --no-start) no_start=yes; shift ;;
        *) die "unknown option: $1" ;;
    esac
done

[ "$(id -u)" = "0" ] || die "run this command as root"
if [ ! -d /opt ] || [ ! -w /opt ]; then
    die "Entware /opt is missing or read-only"
fi
case "$(uname -m)" in
    aarch64|arm64) ;;
    *) die "this package requires ARM64, detected: $(uname -m)" ;;
esac
command -v opkg >/dev/null 2>&1 || die "Entware opkg was not found"

opkg update || die "opkg update failed"
opkg install ca-bundle ca-certificates curl python3 || die "dependency installation failed"
command -v sha256sum >/dev/null 2>&1 || opkg install coreutils-sha256sum \
    || die "sha256sum is required"

case "$repository" in
    */*) ;;
    *) die "repository must use owner/repository" ;;
esac
[ -n "$manifest_url" ] || manifest_url="https://github.com/$repository/releases/latest/download/manifest.tsv"
case "$manifest_url" in
    https://*) ;;
    *) die "manifest URL must use HTTPS" ;;
esac

temporary_dir=$(mktemp -d /opt/tmp/olcrtc-bootstrap.XXXXXX) \
    || die "failed to create temporary directory"
manifest="$temporary_dir/manifest.tsv"
curl -fL --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 300 \
    --retry 3 --retry-delay 2 -o "$manifest" "$manifest_url" \
    || die "manifest download failed"

asset_fields=$(python3 - "$manifest" "$repository" <<'PY'
# ai-generated: validate bootstrap metadata without downloading executable parser code.
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
expected_repository = sys.argv[2]
if path.stat().st_size > 65536:
    raise SystemExit("manifest is too large")
raw = path.read_bytes()
if b"\r" in raw or b"\x00" in raw:
    raise SystemExit("manifest contains forbidden bytes")
text = raw.decode("utf-8")
keys = {
    "manifest_version", "version", "wire", "config_schema", "source_repository",
    "source_commit", "upstream_repository", "upstream_commit", "go_version",
}
scalars = {}
assets = {}
safe_repo = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*/[A-Za-z0-9][A-Za-z0-9._+-]*")
safe_version = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
safe_file = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
hex40 = re.compile(r"[0-9a-f]{40}")
hex64 = re.compile(r"[0-9a-f]{64}")
for number, line in enumerate(text.splitlines(), 1):
    if not line or line.startswith("#"):
        continue
    fields = line.split("\t")
    if fields[0] == "asset":
        if len(fields) != 7:
            raise SystemExit(f"invalid asset row at line {number}")
        _, kind, system, arch, filename, size, digest = fields
        identity = (kind, system, arch)
        if identity in assets or not safe_file.fullmatch(filename):
            raise SystemExit(f"invalid asset identity at line {number}")
        if not size.isascii() or not size.isdigit() or int(size) <= 0 or not hex64.fullmatch(digest):
            raise SystemExit(f"invalid asset metadata at line {number}")
        assets[identity] = (filename, size, digest)
    else:
        if fields[0] not in keys or len(fields) != 2 or not fields[1] or fields[0] in scalars:
            raise SystemExit(f"invalid scalar row at line {number}")
        scalars[fields[0]] = fields[1]
if set(scalars) != keys:
    raise SystemExit("manifest scalar set is incomplete")
required_assets = {
    ("core", "linux", "amd64"), ("core", "linux", "arm64"),
    ("bundle", "linux", "amd64"), ("bundle", "linux", "arm64"),
}
if set(assets) != required_assets:
    raise SystemExit("manifest must contain exactly four supported assets")
if scalars["manifest_version"] != "1" or scalars["config_schema"] != "1" or scalars["wire"] != "OLC2-OLVC5":
    raise SystemExit("unsupported manifest generation")
if scalars["source_repository"] != expected_repository or not safe_repo.fullmatch(expected_repository):
    raise SystemExit("manifest repository does not match bootstrap repository")
if not safe_repo.fullmatch(scalars["upstream_repository"]):
    raise SystemExit("invalid upstream repository")
if not safe_version.fullmatch(scalars["version"]):
    raise SystemExit("invalid release version")
if not re.fullmatch(r"go[0-9]+(?:\.[0-9]+){1,2}", scalars["go_version"]):
    raise SystemExit("invalid Go version")
if not hex40.fullmatch(scalars["source_commit"]) or not hex40.fullmatch(scalars["upstream_commit"]):
    raise SystemExit("invalid source commit")
filename, size, digest = assets[("bundle", "linux", "arm64")]
print("\t".join((scalars["version"], filename, size, digest)))
PY
) || die "manifest validation failed"
tab=$(printf '\t')
old_ifs=$IFS
IFS=$tab
# shellcheck disable=SC2086 # validated TSV fields require intentional splitting.
set -- $asset_fields
IFS=$old_ifs
[ "$#" -eq 4 ] || die "invalid Keenetic asset row"
version=$1
bundle_name=$2
bundle_size=$3
bundle_sha=$4
bundle="$temporary_dir/$bundle_name"
bundle_url="https://github.com/$repository/releases/download/$version/$bundle_name"
curl -fL --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 600 \
    --retry 3 --retry-delay 2 -o "$bundle" "$bundle_url" \
    || die "Keenetic bundle download failed"
[ "$(wc -c <"$bundle" | tr -d '[:space:]')" = "$bundle_size" ] || die "bundle size mismatch"
[ "$(sha256sum "$bundle" | awk '{print $1}')" = "$bundle_sha" ] || die "bundle SHA-256 mismatch"

bundle_dir="$temporary_dir/bundle"
mkdir "$bundle_dir"
python3 - "$bundle" "$bundle_dir" <<'PY'
# ai-generated: safely extract only regular files and directories below the bundle root.
import pathlib
import tarfile
import sys

archive_path = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2]).resolve()
with tarfile.open(archive_path, "r:gz") as archive:
    members = archive.getmembers()
    if not members or len(members) > 100:
        raise SystemExit("bundle has an invalid number of entries")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise SystemExit(f"unsafe bundle entry: {member.name}")
        target = destination.joinpath(*path.parts).resolve()
        if destination not in target.parents and target != destination:
            raise SystemExit(f"bundle entry escapes destination: {member.name}")
    archive.extractall(destination, members=members, filter="data")
PY
[ -f "$bundle_dir/install.sh" ] || die "bundle does not contain install.sh"

set -- --manifest-file "$manifest" --manifest-url "$manifest_url"
[ -z "$uri_file" ] || set -- "$@" --uri-file "$uri_file"
[ "$no_start" = no ] || set -- "$@" --no-start
sh "$bundle_dir/install.sh" "$@"
