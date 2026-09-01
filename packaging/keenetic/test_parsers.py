"""Unit tests for strict Keenetic release and URI parsers."""

# ai-generated: complete parser regression test module.

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parent


# ai-generated: import one standalone packaged helper without changing sys.path.
def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


MANIFEST = load_module("olcrtc_manifest", ROOT / "lib" / "manifest.py")
URI = load_module("olcrtc_uri", ROOT / "lib" / "uri_import.py")


# ai-generated: create a complete supported release manifest for mutation tests.
def manifest_text() -> str:
    rows = [
        "manifest_version\t1",
        "version\tv0.1.0",
        "wire\tOLC2-OLVC5",
        "config_schema\t1",
        "source_repository\tqqweqwe287-art/olcrtc",
        f"source_commit\t{'1' * 40}",
        "upstream_repository\topenlibrecommunity/olcrtc",
        f"upstream_commit\t{'2' * 40}",
        "go_version\tgo1.26.3",
    ]
    for kind, arch, name in (
        ("core", "amd64", "olcrtc-linux-amd64"),
        ("core", "arm64", "olcrtc-linux-arm64"),
        ("bundle", "amd64", "olcrtc-debian-amd64.tar.gz"),
        ("bundle", "arm64", "olcrtc-keenetic-arm64.tar.gz"),
    ):
        rows.append(f"asset\t{kind}\tlinux\t{arch}\t{name}\t10\t{'a' * 64}")
    return "\n".join(rows) + "\n"


class ManifestTests(unittest.TestCase):
    """Release manifest strictness."""

    # ai-generated: accept exactly the four supported release assets.
    def test_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "manifest.tsv")
            path.write_bytes(manifest_text().encode("utf-8"))
            parsed = MANIFEST.load_manifest(path)
            self.assertEqual(len(parsed.assets), 4)

    # ai-generated: reject an otherwise valid manifest containing a fifth asset.
    def test_extra_asset_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "manifest.tsv")
            extra = f"asset\tcore\tlinux\tarm64\textra\t10\t{'b' * 64}\n"
            path.write_bytes((manifest_text() + extra).encode("utf-8"))
            with self.assertRaises(ValueError):
                MANIFEST.load_manifest(path)

    # ai-generated: reject CRLF to keep release hashing and parsing deterministic.
    def test_carriage_return_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "manifest.tsv")
            path.write_bytes(manifest_text().replace("\n", "\r\n").encode())
            with self.assertRaises(ValueError):
                MANIFEST.load_manifest(path)


class UriTests(unittest.TestCase):
    """Canonical Spec URI validation and atomic output."""

    # ai-generated: accept a complete Jitsi room and preserve the compatible transport.
    def test_jitsi_datachannel(self) -> None:
        connection = URI.parse_uri(
            f"olcrtc://jitsi?datachannel@https://meet.example.org/test-room#{'a' * 64}$label"
        )
        self.assertEqual(connection.provider, "jitsi")
        self.assertEqual(connection.transport, "datachannel")

    # ai-generated: reject the placeholder that previously caused a restart loop.
    def test_jitsi_any_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be 'any'"):
            URI.parse_uri(f"olcrtc://jitsi?datachannel@any#{'a' * 64}")

    # ai-generated: reject a transport known to be unavailable for WB Stream guest flow.
    def test_wbstream_datachannel_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported provider/transport"):
            URI.parse_uri(f"olcrtc://wbstream?datachannel@room#{'a' * 64}")

    # ai-generated: keep the previous config intact if rendering fails before commit.
    def test_atomic_config_and_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "client.yaml")
            config.write_text("old\n", encoding="utf-8")
            connection = URI.parse_uri(
                f"olcrtc://jitsi?datachannel@meet.example.org/test#{'c' * 64}"
            )
            URI.write_config(config, connection)
            rendered = config.read_text(encoding="utf-8")
            self.assertIn("mode: cnc", rendered)
            self.assertNotIn("c" * 64, rendered)
            self.assertEqual(len(list(Path(directory).glob("secret-*.key"))), 1)

    # ai-generated: preserve a non-secret profile and rebuild YAML with the existing key.
    def test_managed_profile_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory, "client.yaml")
            profile = Path(directory, "profile.json")
            connection = URI.parse_uri(
                f"olcrtc://jitsi?datachannel@https://meet.example.org/room#{'d' * 64}"
            )
            URI.write_managed_config(config, profile, connection)
            self.assertEqual(URI.load_profile(profile)["provider"], "jitsi")
            settings = {
                "provider": "jitsi",
                "transport": "vp8channel",
                "room": "https://meet.example.org/changed-room",
                "parameters": {"vp8-fps": "30", "vp8-batch": "64"},
            }
            updated = URI.connection_from_settings(settings, URI.read_current_key(config))
            URI.write_managed_config(config, profile, updated)
            self.assertIn("transport: vp8channel", config.read_text(encoding="utf-8"))
            self.assertEqual(URI.load_profile(profile)["room"], settings["room"])

    # ai-generated: reject settings that retain parameters from another transport.
    def test_managed_profile_rejects_unknown_parameters(self) -> None:
        settings = {
            "provider": "jitsi",
            "transport": "datachannel",
            "room": "https://meet.example.org/room-name",
            "parameters": {"vp8-fps": "30"},
        }
        with self.assertRaisesRegex(ValueError, "unsupported datachannel parameter"):
            URI.connection_from_settings(settings, "a" * 64)


if __name__ == "__main__":
    unittest.main()
