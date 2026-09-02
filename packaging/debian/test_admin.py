"""Tests for the isolated Debian administration UI."""

# ai-generated: security and configuration tests for the Debian UI helper.

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("olcrtc-admin.py")
SPEC = importlib.util.spec_from_file_location("olcrtc_native_admin", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ADMIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADMIN)


class PasswordTests(unittest.TestCase):
    """Credential hashing behavior."""

    # ai-generated: accept only the password used to create a salted verifier.
    def test_password_round_trip(self) -> None:
        encoded = ADMIN.hash_password("correct horse battery staple")
        self.assertTrue(ADMIN.verify_password("correct horse battery staple", encoded))
        self.assertFalse(ADMIN.verify_password("incorrect password", encoded))
        self.assertNotIn("correct horse", encoded)


class ConfigTests(unittest.TestCase):
    """Managed server schema and URI behavior."""

    # ai-generated: create, parse and export one valid managed Jitsi instance.
    def test_managed_config_and_uri(self) -> None:
        original = ADMIN.CONFIG_DIR
        try:
            with tempfile.TemporaryDirectory() as directory:
                ADMIN.CONFIG_DIR = Path(directory)
                values = ADMIN.config_values(
                    {
                        "instance": "main",
                        "provider": "jitsi",
                        "transport": "datachannel",
                        "room": "https://meet.example.org/room-name",
                        "dns": "8.8.8.8:53",
                    }
                )
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "main.yaml", ADMIN.config_text(values), 0o640)
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "main.key", "a" * 64 + "\n", 0o640)
                self.assertEqual(ADMIN.managed_config("main"), values)
                uri = ADMIN.spec_uri("main", True)
                self.assertTrue(uri.startswith("olcrtc://jitsi?datachannel@"))
                self.assertIn("#" + "a" * 64, uri)
        finally:
            ADMIN.CONFIG_DIR = original

    # ai-generated: reject the broken placeholder and unsafe guest combination.
    def test_rejects_invalid_combinations(self) -> None:
        base = {
            "instance": "main",
            "provider": "jitsi",
            "transport": "datachannel",
            "room": "any",
            "dns": "8.8.8.8:53",
        }
        with self.assertRaises(ValueError):
            ADMIN.config_values(base)
        base.update(provider="wbstream", room="room-name")
        with self.assertRaisesRegex(ValueError, "account token"):
            ADMIN.config_values(base)

    # ai-generated: reject traversal-like systemd instance names.
    def test_rejects_unsafe_instance(self) -> None:
        for value in ("../main", ".hidden", "main/other", "main..other"):
            with self.assertRaises(ValueError):
                ADMIN.instance_name(value)

    # ai-generated: validate and round-trip the shared liveness and traffic fields.
    def test_expert_values_round_trip(self) -> None:
        values = ADMIN.config_values({"instance": "main", "provider": "jitsi", "transport": "datachannel", "room": "https://meet.example.org/room", "dns": "1.1.1.1:53", "traffic_max_payload": "4096", "traffic_min_delay": "5ms", "traffic_max_delay": "30ms", "debug": "true"})
        rendered = ADMIN.config_text(values)
        self.assertIn("max_payload_size: 4096", rendered)
        self.assertIn("max_delay: 30ms", rendered)
        self.assertIn("debug: true", rendered)

    # ai-generated: encode transport settings in the canonical client URI.
    def test_transport_parameters_exported(self) -> None:
        original = ADMIN.CONFIG_DIR
        try:
            with tempfile.TemporaryDirectory() as directory:
                ADMIN.CONFIG_DIR = Path(directory)
                values = ADMIN.config_values({"instance": "video", "provider": "jitsi", "transport": "vp8channel", "room": "https://meet.example.org/room", "dns": "1.1.1.1:53", "transport_fps": "25", "transport_batch": "80"})
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "video.yaml", ADMIN.config_text(values), 0o640)
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "video.key", "a" * 64 + "\n", 0o640)
                uri = ADMIN.spec_uri("video", True)
                self.assertIn("vp8channel<vp8-fps=25&vp8-batch=80>", uri)
        finally:
            ADMIN.CONFIG_DIR = original

    # ai-generated: reject inverted traffic pacing before touching a config file.
    def test_expert_values_reject_inverted_delay(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be lower"):
            ADMIN.config_values({"instance": "main", "provider": "jitsi", "transport": "datachannel", "room": "https://meet.example.org/room", "dns": "1.1.1.1:53", "traffic_min_delay": "30ms", "traffic_max_delay": "5ms"})

    # ai-generated: preserve and restore only the two fixed files for an instance.
    def test_backup_and_restore_instance(self) -> None:
        original_config = ADMIN.CONFIG_DIR
        original_backup = ADMIN.BACKUP_DIR
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                ADMIN.CONFIG_DIR = root / "config"
                ADMIN.BACKUP_DIR = root / "backups"
                ADMIN.CONFIG_DIR.mkdir()
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "main.yaml", "old yaml\n", 0o640)
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "main.key", "a" * 64 + "\n", 0o640)
                backup = ADMIN.backup_instance("main", "before-save")
                ADMIN.atomic_write(ADMIN.CONFIG_DIR / "main.yaml", "new yaml\n", 0o640)
                ADMIN.restore_instance("main", backup)
                self.assertEqual((ADMIN.CONFIG_DIR / "main.yaml").read_text(), "old yaml\n")
                self.assertEqual((ADMIN.CONFIG_DIR / "main.key").read_text().strip(), "a" * 64)
                metadata = (backup / "backup.json").read_text()
                self.assertIn('"schema": 1', metadata)
                (backup / "main.yaml").write_text("tampered\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "checksum"):
                    ADMIN.restore_instance("main", backup)
        finally:
            ADMIN.CONFIG_DIR = original_config
            ADMIN.BACKUP_DIR = original_backup


class RedactionTests(unittest.TestCase):
    """Secret filtering."""

    # ai-generated: remove keys and credential-like fields from displayed logs.
    def test_redaction(self) -> None:
        secret = "b" * 64
        output = ADMIN.redact(f"key={secret}\npassword=hunter2\ntoken=abc")
        self.assertNotIn(secret, output)
        self.assertNotIn("hunter2", output)
        self.assertNotIn("abc", output)


class AdminSettingsTests(unittest.TestCase):
    """Public URL and hashed subscription state."""

    # ai-generated: accept only a plain HTTPS origin for generated links.
    def test_public_base_url(self) -> None:
        self.assertEqual(ADMIN.public_base_url("https://vpn.example.org:8443/"), "https://vpn.example.org:8443")
        for value in ("http://vpn.example.org", "https://user@vpn.example.org", "https://vpn.example.org/path", "https://vpn.example.org/?token=x"):
            with self.assertRaises(ValueError):
                ADMIN.public_base_url(value)

    # ai-generated: persist a subscription index containing only one-way slug hashes.
    def test_admin_settings_round_trip(self) -> None:
        original = ADMIN.ADMIN_SETTINGS_PATH
        try:
            with tempfile.TemporaryDirectory() as directory:
                ADMIN.ADMIN_SETTINGS_PATH = Path(directory) / "admin.json"
                digest = "a" * 64
                payload = {"schema": 1, "public_base_url": "https://vpn.example.org", "subscriptions": {digest: "main"}}
                ADMIN.save_admin_settings(payload)
                loaded = ADMIN.admin_settings()
                self.assertEqual(loaded, payload)
                self.assertNotIn("raw-subscription-slug", ADMIN.ADMIN_SETTINGS_PATH.read_text())
        finally:
            ADMIN.ADMIN_SETTINGS_PATH = original


if __name__ == "__main__":
    unittest.main()
