#!/bin/sh
# ai-generated: deterministic smoke tests for release asset assembly.

set -eu

# ai-generated: print a test failure and stop.
fail() {
	printf 'test-release: %s\n' "$*" >&2
	exit 1
}

# ai-generated: require an exact fixed manifest row.
expect_row() {
	grep -F -x "$1" "$MANIFEST" >/dev/null || fail "missing manifest row: $1"
}

ROOT=$(CDPATH='' cd -- "$(dirname "$0")/../.." && pwd)
TMP_ROOT=${TMPDIR:-/tmp}/olcrtc-release-test-$$
BUILD_DIR=$TMP_ROOT/build
BUNDLE_DIR=$TMP_ROOT/bundles
DIST_DIR=$TMP_ROOT/dist
SOURCE_SHA=0123456789abcdef0123456789abcdef01234567
TAB=$(printf '\t')

trap 'rm -rf "$TMP_ROOT"' EXIT HUP INT TERM
mkdir -p "$BUILD_DIR" "$BUNDLE_DIR"
printf 'amd64-binary\n' >"$BUILD_DIR/olcrtc-linux-amd64"
printf 'arm64-binary\n' >"$BUILD_DIR/olcrtc-linux-arm64"
printf 'debian-bundle\n' >"$BUNDLE_DIR/olcrtc-debian-amd64.tar.gz"
printf 'keenetic-bundle\n' >"$BUNDLE_DIR/olcrtc-keenetic-arm64.tar.gz"

SOURCE_COMMIT=$SOURCE_SHA \
	GO_VERSION=go1.26.3 \
	UPSTREAM_FILE=$ROOT/packaging/release/UPSTREAM_COMMIT \
	sh "$ROOT/packaging/release/assemble-assets.sh" \
	"$BUILD_DIR" "$BUNDLE_DIR" "$DIST_DIR" v0.0.0-test

MANIFEST=$DIST_DIR/manifest.tsv
[ -f "$MANIFEST" ] || fail 'manifest.tsv was not created'
[ "$(awk -F '\t' '$1 == "asset" { count++ } END { print count + 0 }' "$MANIFEST")" -eq 4 ] || \
	fail 'manifest must contain exactly four asset rows'
[ "$(awk -F '\t' '$1 == "asset" && NF != 7 { count++ } END { print count + 0 }' "$MANIFEST")" -eq 0 ] || \
	fail 'every asset row must contain exactly seven fields'
expect_row "manifest_version${TAB}1"
expect_row "version${TAB}v0.0.0-test"
expect_row "wire${TAB}OLC2-OLVC5"
expect_row "config_schema${TAB}1"
expect_row "source_commit${TAB}$SOURCE_SHA"

if command -v sha256sum >/dev/null 2>&1; then
	(cd "$DIST_DIR" && sha256sum -c SHA256SUMS >/dev/null) || fail 'checksum verification failed'
fi

if SOURCE_COMMIT=bad UPSTREAM_FILE=$ROOT/packaging/release/UPSTREAM_COMMIT \
	sh "$ROOT/packaging/release/assemble-assets.sh" \
	"$BUILD_DIR" "$BUNDLE_DIR" "$TMP_ROOT/rejected" v0.0.0 >/dev/null 2>&1; then
	fail 'malformed source commit was accepted'
fi

printf 'test-release: ok\n'
