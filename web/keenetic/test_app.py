"""Tests for the Keenetic web control plane."""

# ai-generated: complete web control plane unit test module.

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("app.py")
SPEC = importlib.util.spec_from_file_location("olcrtc_keenetic_web", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("unable to load app module")
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class PasswordTests(unittest.TestCase):
    """Password hashing behavior."""

    # ai-generated: verify correct and incorrect credentials.
    def test_password_round_trip(self) -> None:
        encoded = APP.hash_password("correct horse battery")
        self.assertTrue(APP.verify_password("correct horse battery", encoded))
        self.assertFalse(APP.verify_password("wrong password", encoded))

    # ai-generated: reject short management passwords.
    def test_short_password_rejected(self) -> None:
        with self.assertRaises(ValueError):
            APP.hash_password("short")


class RedactionTests(unittest.TestCase):
    """Secret redaction behavior."""

    # ai-generated: redact URI and YAML secrets.
    def test_redacts_hex_and_yaml(self) -> None:
        secret = "a" * 64
        output = APP.redact(
            f'uri #{secret}$label\nkey: {secret}\npassword: value\n'
            'OLCRTC_ADMIN_TOKEN=manager-token\n{"token":"json-token"}'
        )
        self.assertNotIn(secret, output)
        self.assertNotIn("value", output)
        self.assertNotIn("manager-token", output)
        self.assertNotIn("json-token", output)
        self.assertIn("[redacted-64hex]", output)


class SettingsTests(unittest.TestCase):
    """Settings validation behavior."""

    # ai-generated: reject wildcard listeners even with LAN permission.
    def test_wildcard_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "web.json")
            path.write_text(
                '{"bind":"0.0.0.0","port":8091,"allow_lan":true,"username":"admin","password_hash":"x"}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                APP.load_settings(path)

    # ai-generated: require explicit permission for a LAN bind.
    def test_lan_requires_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "web.json")
            path.write_text(
                '{"bind":"192.0.2.1","port":8091,"allow_lan":false,"username":"admin","password_hash":"x"}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                APP.load_settings(path)

    # ai-generated: reject accidental public WAN listeners even with LAN permission.
    def test_public_bind_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "web.json")
            path.write_text(
                '{"bind":"8.8.8.8","port":8091,"allow_lan":true,"username":"admin","password_hash":"x"}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                APP.load_settings(path)

    # ai-generated: accept an explicit RFC1918 listener for the router LAN.
    def test_private_lan_bind_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "web.json")
            path.write_text(
                '{"bind":"192.168.9.1","port":8091,"allow_lan":true,"username":"admin","password_hash":"x"}',
                encoding="utf-8",
            )
            self.assertEqual(APP.load_settings(path).bind, "192.168.9.1")

    # ai-generated: reject string booleans that could silently enable LAN access.
    def test_allow_lan_requires_json_boolean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "web.json")
            path.write_text(
                '{"bind":"192.168.9.1","port":8091,"allow_lan":"false","username":"admin","password_hash":"x"}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                APP.load_settings(path)

    # ai-generated: initialize settings from a protected installer password file.
    def test_password_file_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "web.json"
            password_file = root / "password"
            password_file.write_text("installer-generated-password\n", encoding="utf-8")
            APP.initialize_settings(path, "127.0.0.1", 8091, False, password_file)
            settings = APP.load_settings(path)
            self.assertTrue(APP.verify_password("installer-generated-password", settings.password_hash))


if __name__ == "__main__":
    unittest.main()
