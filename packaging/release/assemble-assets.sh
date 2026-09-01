#!/bin/sh
# ai-generated: release asset assembly and manifest validation for the fork.

set -eu

# ai-generated: print a release assembly error and stop.
die() {
	printf 'release: %s\n' "$*" >&2
	exit 1
}

# ai-generated: require a regular non-empty input file.
require_file() {
	[ -f "$1" ] || die "missing file: $1"
	[ -s "$1" ] || die "empty file: $1"
}

# ai-generated: return a portable byte count for one file.
file_size() {
	wc -c <"$1" | tr -d '[:space:]'
}

# ai-generated: calculate SHA-256 with a tool available on common build hosts.
file_sha256() {
	if command -v sha256sum >/dev/null 2>&1; then
		sha256sum "$1" | awk '{print $1}'
		return
	fi
	if command -v shasum >/dev/null 2>&1; then
		shasum -a 256 "$1" | awk '{print $1}'
		return
	fi
	die 'sha256sum or shasum is required'
}

# ai-generated: reject values that cannot safely appear in a strict TSV field.
validate_field() {
	case "$2" in
		''|*[!A-Za-z0-9._+/@:-]*) die "invalid $1: $2" ;;
	esac
}

# ai-generated: require exactly one slash in an owner/repository slug.
validate_repository() {
	case "$2" in
		*/*/*|/*|*/|'') die "invalid $1: $2" ;;
		*/*) ;;
		*) die "invalid $1: $2" ;;
	esac
	validate_field "$1" "$2"
}

# ai-generated: reject malformed Git commit identifiers.
validate_commit() {
	case "$2" in
		*[!0-9a-f]*|'') die "invalid $1: $2" ;;
	esac
	[ "${#2}" -eq 40 ] || die "$1 must contain 40 hexadecimal characters"
}

# ai-generated: append one validated asset row to the release manifest.
append_asset() {
	type=$1
	os=$2
	arch=$3
	path=$4
	name=$(basename "$path")
	[ "$name" = "$path" ] || die "asset path must be a basename: $path"
	validate_field 'asset name' "$name"
	size=$(file_size "$DIST_DIR/$name")
	sha=$(file_sha256 "$DIST_DIR/$name")
	printf 'asset\t%s\t%s\t%s\t%s\t%s\t%s\n' \
		"$type" "$os" "$arch" "$name" "$size" "$sha" >>"$MANIFEST"
}

[ "$#" -eq 4 ] || die 'usage: assemble-assets.sh BUILD_DIR BUNDLE_DIR DIST_DIR VERSION'

BUILD_DIR=$1
BUNDLE_DIR=$2
DIST_DIR=$3
VERSION=$4
SOURCE_COMMIT=${SOURCE_COMMIT:-$(git rev-parse HEAD)}
SOURCE_REPOSITORY=${SOURCE_REPOSITORY:-qqweqwe287-art/olcrtc}
UPSTREAM_REPOSITORY=${UPSTREAM_REPOSITORY:-openlibrecommunity/olcrtc}
GO_VERSION=${GO_VERSION:-$(go env GOVERSION)}
UPSTREAM_FILE=${UPSTREAM_FILE:-packaging/release/UPSTREAM_COMMIT}

validate_field version "$VERSION"
validate_repository source_repository "$SOURCE_REPOSITORY"
validate_repository upstream_repository "$UPSTREAM_REPOSITORY"
validate_field go_version "$GO_VERSION"
validate_commit source_commit "$SOURCE_COMMIT"
require_file "$UPSTREAM_FILE"
UPSTREAM_COMMIT=$(tr -d '\r\n' <"$UPSTREAM_FILE")
validate_commit upstream_commit "$UPSTREAM_COMMIT"

CORE_AMD64=olcrtc-linux-amd64
CORE_ARM64=olcrtc-linux-arm64
DEBIAN_BUNDLE=olcrtc-debian-amd64.tar.gz
KEENETIC_BUNDLE=olcrtc-keenetic-arm64.tar.gz

require_file "$BUILD_DIR/$CORE_AMD64"
require_file "$BUILD_DIR/$CORE_ARM64"
require_file "$BUNDLE_DIR/$DEBIAN_BUNDLE"
require_file "$BUNDLE_DIR/$KEENETIC_BUNDLE"
[ ! -e "$DIST_DIR" ] || die "output directory already exists: $DIST_DIR"
mkdir -p "$DIST_DIR"

cp "$BUILD_DIR/$CORE_AMD64" "$DIST_DIR/$CORE_AMD64"
cp "$BUILD_DIR/$CORE_ARM64" "$DIST_DIR/$CORE_ARM64"
cp "$BUNDLE_DIR/$DEBIAN_BUNDLE" "$DIST_DIR/$DEBIAN_BUNDLE"
cp "$BUNDLE_DIR/$KEENETIC_BUNDLE" "$DIST_DIR/$KEENETIC_BUNDLE"
chmod 0755 "$DIST_DIR/$CORE_AMD64" "$DIST_DIR/$CORE_ARM64"

MANIFEST=$DIST_DIR/manifest.tsv
{
    printf 'manifest_version\t1\n'
    printf 'version\t%s\n' "$VERSION"
    printf 'wire\tOLC2-OLVC5\n'
    printf 'config_schema\t1\n'
    printf 'source_repository\t%s\n' "$SOURCE_REPOSITORY"
    printf 'source_commit\t%s\n' "$SOURCE_COMMIT"
    printf 'upstream_repository\t%s\n' "$UPSTREAM_REPOSITORY"
    printf 'upstream_commit\t%s\n' "$UPSTREAM_COMMIT"
    printf 'go_version\t%s\n' "$GO_VERSION"
} >"$MANIFEST"

append_asset core linux amd64 "$CORE_AMD64"
append_asset core linux arm64 "$CORE_ARM64"
append_asset bundle linux amd64 "$DEBIAN_BUNDLE"
append_asset bundle linux arm64 "$KEENETIC_BUNDLE"

(
	cd "$DIST_DIR"
	file_sha256 "$CORE_AMD64" | awk -v file="$CORE_AMD64" '{print $1 "  " file}'
	file_sha256 "$CORE_ARM64" | awk -v file="$CORE_ARM64" '{print $1 "  " file}'
	file_sha256 "$DEBIAN_BUNDLE" | awk -v file="$DEBIAN_BUNDLE" '{print $1 "  " file}'
	file_sha256 "$KEENETIC_BUNDLE" | awk -v file="$KEENETIC_BUNDLE" '{print $1 "  " file}'
	file_sha256 manifest.tsv | awk '{print $1 "  manifest.tsv"}'
) >"$DIST_DIR/SHA256SUMS"

if command -v sha256sum >/dev/null 2>&1; then
	(cd "$DIST_DIR" && sha256sum -c SHA256SUMS)
fi

printf 'release: assembled %s from source %s\n' "$VERSION" "$SOURCE_COMMIT"
