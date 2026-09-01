#!/usr/bin/env python3
# ai-generated: strict parser for the release manifest used by router tooling.

"""Validate and query the olcRTC release manifest without sourcing it."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SCALAR_KEYS = {
    "manifest_version",
    "version",
    "wire",
    "config_schema",
    "source_repository",
    "source_commit",
    "upstream_repository",
    "upstream_commit",
    "go_version",
}
HEX_40 = re.compile(r"[0-9a-f]{40}")
HEX_64 = re.compile(r"[0-9a-f]{64}")
SAFE_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+/-]*")
SAFE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
SAFE_GO_VERSION = re.compile(r"go[0-9]+(?:\.[0-9]+){1,2}")
REQUIRED_ASSETS = {
    ("core", "linux", "amd64"),
    ("core", "linux", "arm64"),
    ("bundle", "linux", "amd64"),
    ("bundle", "linux", "arm64"),
}


# ai-generated: immutable asset row returned by the strict parser.
@dataclass(frozen=True)
class Asset:
    kind: str
    system: str
    arch: str
    filename: str
    size: int
    sha256: str


# ai-generated: parsed manifest value object.
@dataclass(frozen=True)
class Manifest:
    scalars: dict[str, str]
    assets: tuple[Asset, ...]


# ai-generated: validate a repository slug used to build GitHub release URLs.
def validate_repository(value: str, field: str) -> None:
    parts = value.split("/")
    if len(parts) != 2 or not all(SAFE_VALUE.fullmatch(part) for part in parts):
        raise ValueError(f"{field}: expected owner/repository")


# ai-generated: validate scalar values after structural parsing.
def validate_scalars(values: dict[str, str]) -> None:
    missing = SCALAR_KEYS - values.keys()
    if missing:
        raise ValueError(f"missing scalar rows: {', '.join(sorted(missing))}")
    if values["manifest_version"] != "1":
        raise ValueError("manifest_version: unsupported value")
    if values["config_schema"] != "1":
        raise ValueError("config_schema: unsupported value")
    if values["wire"] != "OLC2-OLVC5":
        raise ValueError("wire: unsupported value")
    if not SAFE_VERSION.fullmatch(values["version"]):
        raise ValueError("version: unsafe release tag")
    if not SAFE_GO_VERSION.fullmatch(values["go_version"]):
        raise ValueError("go_version: invalid value")
    validate_repository(values["source_repository"], "source_repository")
    validate_repository(values["upstream_repository"], "upstream_repository")
    for field in ("source_commit", "upstream_commit"):
        if not HEX_40.fullmatch(values[field]):
            raise ValueError(f"{field}: expected lowercase 40-character hex")


# ai-generated: validate one release asset without trusting paths from the manifest.
def parse_asset(fields: list[str], line_number: int) -> Asset:
    if len(fields) != 7:
        raise ValueError(f"line {line_number}: asset row must contain 7 fields")
    _, kind, system, arch, filename, size_text, sha256 = fields
    if kind not in {"core", "bundle"}:
        raise ValueError(f"line {line_number}: unknown asset kind")
    if system != "linux":
        raise ValueError(f"line {line_number}: unsupported operating system")
    if arch not in {"amd64", "arm64"}:
        raise ValueError(f"line {line_number}: unsupported architecture")
    if filename in {".", ".."} or not SAFE_FILE.fullmatch(filename):
        raise ValueError(f"line {line_number}: asset must be a safe basename")
    if not size_text.isascii() or not size_text.isdigit() or int(size_text) <= 0:
        raise ValueError(f"line {line_number}: invalid asset size")
    if not HEX_64.fullmatch(sha256):
        raise ValueError(f"line {line_number}: invalid SHA-256")
    return Asset(kind, system, arch, filename, int(size_text), sha256)


# ai-generated: parse a UTF-8 TSV manifest and reject unknown or duplicate rows.
def load_manifest(path: Path) -> Manifest:
    try:
        raw = path.read_bytes()
        if len(raw) > 65536:
            raise ValueError("manifest is too large")
        if b"\r" in raw or b"\x00" in raw:
            raise ValueError("manifest contains forbidden bytes")
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("manifest is not valid UTF-8") from exc

    scalars: dict[str, str] = {}
    assets: list[Asset] = []
    identities: set[tuple[str, str, str]] = set()
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line or raw_line.startswith("#"):
            continue
        fields = raw_line.split("\t")
        key = fields[0]
        if key == "asset":
            asset = parse_asset(fields, line_number)
            identity = (asset.kind, asset.system, asset.arch)
            if identity in identities:
                raise ValueError(f"line {line_number}: duplicate asset row")
            identities.add(identity)
            assets.append(asset)
            continue
        if key not in SCALAR_KEYS:
            raise ValueError(f"line {line_number}: unknown scalar row {key!r}")
        if len(fields) != 2 or not fields[1]:
            raise ValueError(f"line {line_number}: scalar row must contain 2 fields")
        if key in scalars:
            raise ValueError(f"line {line_number}: duplicate scalar row {key!r}")
        scalars[key] = fields[1]

    validate_scalars(scalars)
    if identities != REQUIRED_ASSETS:
        raise ValueError("manifest must contain exactly four supported assets")
    return Manifest(scalars, tuple(assets))


# ai-generated: find exactly one requested asset row.
def find_asset(manifest: Manifest, kind: str, system: str, arch: str) -> Asset:
    matches = [
        asset
        for asset in manifest.assets
        if (asset.kind, asset.system, asset.arch) == (kind, system, arch)
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one asset for {kind}/{system}/{arch}")
    return matches[0]


# ai-generated: command-line entrypoint kept small for BusyBox shell callers.
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("command", choices=("validate", "get", "asset"))
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "validate":
            if args.arguments:
                raise ValueError("validate takes no arguments")
            return 0
        if args.command == "get":
            if len(args.arguments) != 1 or args.arguments[0] not in SCALAR_KEYS:
                raise ValueError("get requires one known scalar key")
            print(manifest.scalars[args.arguments[0]])
            return 0
        if len(args.arguments) != 3:
            raise ValueError("asset requires kind, system and architecture")
        asset = find_asset(manifest, *args.arguments)
        print(f"{asset.filename}\t{asset.size}\t{asset.sha256}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
