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


if __name__ == "__main__":
    unittest.main()

