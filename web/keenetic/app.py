#!/usr/bin/env python3
"""Small authenticated web control plane for olcRTC on Entware."""

# ai-generated: complete Keenetic web control plane module.

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import http.cookies
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PASSWORD_SCHEME = "scrypt-v1"
SESSION_TTL_SECONDS = 30 * 60
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_ATTEMPTS = 5
MAX_BODY_BYTES = 128 * 1024
HEX_SECRET_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
YAML_SECRET_RE = re.compile(r"(?im)^(\s*(?:key|token|pass|password)\s*:\s*).+$")
ENV_SECRET_RE = re.compile(
    r"(?im)^(\s*(?:OLCRTC_(?:KEY|AUTH_TOKEN|ADMIN_PASS|ADMIN_TOKEN)|AUTHORIZATION)\s*=\s*).+$"
)
JSON_SECRET_RE = re.compile(
    r'(?i)("(?:key|token|pass|password|password_hash)"\s*:\s*)"[^"]*"'
)
LAN_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


@dataclass(frozen=True)
class Settings:
    """Validated web service settings."""

    bind: str
    port: int
    allow_lan: bool
    username: str
    password_hash: str
    client_service: str
    doctor: str
    config_helper: str
    client_config: str
    config_path: str


class ControlState:
    """Mutable authenticated session state."""

    # ai-generated: initialize bounded in-memory authentication state.
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sessions: dict[str, tuple[float, str]] = {}
        self.attempts: defaultdict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    # ai-generated: create a short-lived session and CSRF token.
    def create_session(self) -> tuple[str, str]:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        now = time.monotonic()
        with self.lock:
            self._prune_sessions(now)
            self.sessions[token] = (now + SESSION_TTL_SECONDS, csrf)
        return token, csrf

    # ai-generated: resolve and refresh a session without leaking token details.
    def get_session(self, token: str) -> str | None:
        now = time.monotonic()
        with self.lock:
            self._prune_sessions(now)
            current = self.sessions.get(token)
            if current is None:
                return None
            _, csrf = current
            self.sessions[token] = (now + SESSION_TTL_SECONDS, csrf)
            return csrf

    # ai-generated: remove one authenticated session.
    def delete_session(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)

    # ai-generated: rate-limit password attempts per source address.
    def may_login(self, address: str) -> bool:
        now = time.monotonic()
        with self.lock:
            attempts = self.attempts[address]
            while attempts and attempts[0] <= now - LOGIN_WINDOW_SECONDS:
                attempts.popleft()
            return len(attempts) < LOGIN_ATTEMPTS

    # ai-generated: record a failed login attempt.
    def record_failure(self, address: str) -> None:
        with self.lock:
            self.attempts[address].append(time.monotonic())

    # ai-generated: clear failures after a valid login.
    def clear_failures(self, address: str) -> None:
        with self.lock:
            self.attempts.pop(address, None)

    # ai-generated: remove expired sessions while holding the state lock.
    def _prune_sessions(self, now: float) -> None:
        expired = [token for token, value in self.sessions.items() if value[0] <= now]
        for token in expired:
            self.sessions.pop(token, None)


class ControlServer(ThreadingHTTPServer):
    """HTTP server carrying the control state."""

    daemon_threads = True

    # ai-generated: attach settings state to the HTTP server.
    def __init__(self, address: tuple[str, int], state: ControlState) -> None:
        super().__init__(address, ControlHandler)
        self.control_state = state


class ControlHandler(BaseHTTPRequestHandler):
    """Authenticated JSON API and embedded single-page UI."""

    server_version = "olcrtc-keenetic-web/0.1"

    # ai-generated: suppress default request lines that could contain user input.
    def log_message(self, request_format: str, *args: Any) -> None:
        del request_format, args

    # ai-generated: route read-only HTTP requests.
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._html(INDEX_HTML)
            return
        if self.path == "/api/session":
            csrf = self._authenticated_csrf()
            self._json({"authenticated": csrf is not None, "csrf": csrf or ""})
            return
        if self.path == "/api/status":
            if not self._require_auth():
                return
            self._json(self._status_payload())
            return
        if self.path == "/api/logs":
            if not self._require_auth():
                return
            settings = self._state().settings
            result = run_command([settings.client_service, "log", "200"], 8)
            self._json({"ok": result[0], "output": redact(result[1])})
            return
        if self.path == "/api/config":
            if not self._require_auth():
                return
            settings = self._state().settings
            content = read_text(Path(settings.client_config), 64 * 1024)
            self._json({"ok": content is not None, "content": redact(content or "")})
            return
        if self.path == "/api/profile":
            if not self._require_auth():
                return
            helper = self._state().settings.config_helper
            ok, output = run_command([helper, "--show"], 8)
            if not ok:
                self._json({"ok": False, "profile": None, "output": redact(output)})
                return
            try:
                profile = json.loads(output)
            except json.JSONDecodeError:
                self._json({"error": "profile_invalid"}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, "profile": profile})
            return
        self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    # ai-generated: route mutating HTTP requests with origin and CSRF checks.
    def do_POST(self) -> None:  # noqa: N802
        if not self._same_origin():
            self._json({"error": "origin_rejected"}, HTTPStatus.FORBIDDEN)
            return
        payload = self._read_json()
        if payload is None:
            return
        if self.path == "/api/login":
            self._login(payload)
            return
        if not self._require_csrf(payload):
            return
        if self.path == "/api/logout":
            token = self._session_token()
            if token:
                self._state().delete_session(token)
            self._clear_cookie()
            return
        if self.path == "/api/action":
            self._action(payload)
            return
        if self.path == "/api/import-uri":
            self._import_uri(payload)
            return
        if self.path == "/api/settings":
            self._save_settings(payload)
            return
        if self.path == "/api/change-credentials":
            self._change_credentials(payload)
            return
        self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    # ai-generated: authenticate a bounded login request.
    def _login(self, payload: dict[str, Any]) -> None:
        address = self.client_address[0]
        state = self._state()
        if not state.may_login(address):
            self._json({"error": "rate_limited"}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        username = str(payload.get("username", ""))
        password = str(payload.get("password", ""))
        valid_user = hmac.compare_digest(username, state.settings.username)
        valid_password = verify_password(password, state.settings.password_hash)
        if not (valid_user and valid_password):
            state.record_failure(address)
            time.sleep(0.25)
            self._json({"error": "invalid_credentials"}, HTTPStatus.UNAUTHORIZED)
            return
        state.clear_failures(address)
        token, csrf = state.create_session()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header(
            "Set-Cookie",
            f"olcrtc_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}",
        )
        body = json.dumps({"ok": True, "csrf": csrf}).encode()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ai-generated: execute one whitelisted service action without a shell.
    def _action(self, payload: dict[str, Any]) -> None:
        action = str(payload.get("action", ""))
        settings = self._state().settings
        commands = {
            "start": [settings.client_service, "start"],
            "stop": [settings.client_service, "stop"],
            "restart": [settings.client_service, "restart"],
            "probe": [settings.doctor],
            "diagnostics": [settings.doctor, "--quick"],
            "enable-native": ["/opt/lib/olcrtc-keenetic/migration.sh", "enable"],
            "cutover": ["/opt/lib/olcrtc-keenetic/migration.sh", "cutover"],
            "legacy-rollback": ["/opt/lib/olcrtc-keenetic/migration.sh", "rollback"],
            "update": ["/opt/lib/olcrtc-keenetic/upgrade.sh"],
            "binary-rollback": ["/opt/lib/olcrtc-keenetic/rollback.sh"],
            "purge-legacy": ["/opt/lib/olcrtc-keenetic/migration.sh", "purge-legacy"],
        }
        command = commands.get(action)
        if command is None:
            self._json({"error": "action_rejected"}, HTTPStatus.BAD_REQUEST)
            return
        ok, output = run_command(command, 30)
        self._json({"ok": ok, "output": redact(output)}, HTTPStatus.OK if ok else HTTPStatus.BAD_GATEWAY)

    # ai-generated: pass a canonical URI to a fixed validator through stdin.
    def _import_uri(self, payload: dict[str, Any]) -> None:
        uri = str(payload.get("uri", "")).strip()
        if len(uri) > 8192 or not uri.startswith("olcrtc://"):
            self._json({"error": "uri_invalid"}, HTTPStatus.BAD_REQUEST)
            return
        helper = self._state().settings.config_helper
        ok, output = run_command([helper, "--stdin"], 15, uri + "\n")
        self._json({"ok": ok, "output": redact(output)}, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)

    # ai-generated: validate and persist non-secret client settings through the fixed helper.
    def _save_settings(self, payload: dict[str, Any]) -> None:
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            self._json({"error": "profile_required"}, HTTPStatus.BAD_REQUEST)
            return
        encoded = json.dumps(profile, ensure_ascii=False, separators=(",", ":"))
        if len(encoded) > 32768:
            self._json({"error": "profile_too_large"}, HTTPStatus.BAD_REQUEST)
            return
        helper = self._state().settings.config_helper
        ok, output = run_command([helper, "--settings-stdin"], 15, encoded)
        self._json({"ok": ok, "output": redact(output)}, HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)

    # ai-generated: atomically rotate panel credentials and revoke existing sessions.
    def _change_credentials(self, payload: dict[str, Any]) -> None:
        username = str(payload.get("username", ""))
        password = str(payload.get("password", ""))
        confirmation = str(payload.get("confirmation", ""))
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
            self._json({"error": "username_invalid"}, HTTPStatus.BAD_REQUEST)
            return
        if len(password) < 12 or not hmac.compare_digest(password, confirmation):
            self._json({"error": "password_invalid_or_mismatch"}, HTTPStatus.BAD_REQUEST)
            return
        state = self._state()
        path = Path(state.settings.config_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("web config must be an object")
            encoded = hash_password(password)
            raw["username"] = username
            raw["password_hash"] = encoded
            atomic_json(path, raw, 0o600)
            state.settings = replace(state.settings, username=username, password_hash=encoded)
            with state.lock:
                state.sessions.clear()
        except (OSError, ValueError, json.JSONDecodeError):
            self._json({"error": "credential_update_failed"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self._clear_cookie()

    # ai-generated: combine process, SOCKS and diagnostic status.
    def _status_payload(self) -> dict[str, Any]:
        settings = self._state().settings
        service_ok, service_text = run_command([settings.client_service, "status"], 8)
        doctor_ok, doctor_text = run_command([settings.doctor, "--quick"], 15)
        diagnostics: Any = redact(doctor_text)
        return {
            "ok": service_ok and doctor_ok,
            "service_ok": service_ok,
            "service": redact(service_text),
            "diagnostics": diagnostics,
        }

    # ai-generated: parse one bounded JSON object.
    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._json({"error": "body_too_large"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "json_invalid"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._json({"error": "json_object_required"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    # ai-generated: enforce session and CSRF token equality.
    def _require_csrf(self, payload: dict[str, Any]) -> bool:
        csrf = self._authenticated_csrf()
        supplied = str(payload.get("csrf", ""))
        if csrf is None or not hmac.compare_digest(csrf, supplied):
            self._json({"error": "csrf_rejected"}, HTTPStatus.FORBIDDEN)
            return False
        return True

    # ai-generated: reject cross-origin browser mutations.
    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in {f"http://{host}", f"https://{host}"}

    # ai-generated: require an authenticated session.
    def _require_auth(self) -> bool:
        if self._authenticated_csrf() is not None:
            return True
        self._json({"error": "authentication_required"}, HTTPStatus.UNAUTHORIZED)
        return False

    # ai-generated: return CSRF token for a valid session cookie.
    def _authenticated_csrf(self) -> str | None:
        token = self._session_token()
        if not token:
            return None
        return self._state().get_session(token)

    # ai-generated: parse only the expected cookie name.
    def _session_token(self) -> str:
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return ""
        morsel = cookie.get("olcrtc_session")
        return morsel.value if morsel else ""

    # ai-generated: expire the browser session cookie.
    def _clear_cookie(self) -> None:
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Set-Cookie", "olcrtc_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
        body = b'{"ok":true}'
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ai-generated: write a JSON response with security headers.
    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ai-generated: write the embedded application shell.
    def _html(self, content: str) -> None:
        body = content.encode()
        self.send_response(HTTPStatus.OK)
        self._security_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ai-generated: set restrictive browser response policy.
    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    # ai-generated: return typed server state.
    def _state(self) -> ControlState:
        server = self.server
        if not isinstance(server, ControlServer):
            raise RuntimeError("invalid server type")
        return server.control_state


# ai-generated: hash one password with a random salt and bounded scrypt parameters.
def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=1 << 14, r=8, p=1, dklen=32)
    return "$".join(
        [PASSWORD_SCHEME, base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()]
    )


# ai-generated: verify one password in constant time.
def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_text, digest_text = encoded.split("$", 2)
        if scheme != PASSWORD_SCHEME:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=1 << 14, r=8, p=1, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# ai-generated: redact common olcRTC secret forms from diagnostics.
def redact(value: str) -> str:
    value = HEX_SECRET_RE.sub("[redacted-64hex]", value)
    value = YAML_SECRET_RE.sub(r"\1[redacted]", value)
    value = ENV_SECRET_RE.sub(r"\1[redacted]", value)
    return JSON_SECRET_RE.sub(r'\1"[redacted]"', value)


# ai-generated: run one fixed argument vector without invoking a shell.
def run_command(arguments: list[str], timeout: int, stdin: str | None = None) -> tuple[bool, str]:
    if not arguments or not Path(arguments[0]).is_file():
        return False, f"command unavailable: {arguments[0] if arguments else 'empty'}"
    try:
        completed = subprocess.run(
            arguments,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={"PATH": "/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


# ai-generated: read a bounded UTF-8 text file.
def read_text(path: Path, limit: int) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


# ai-generated: write one JSON object with restrictive permissions and atomic replacement.
def atomic_json(path: Path, payload: dict[str, Any], mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


# ai-generated: load and validate persistent web settings.
# ai-generated: permit only loopback or an explicitly enabled RFC1918 listener.
def validate_bind_address(bind: str, allow_lan: bool) -> None:
    if bind == "localhost":
        return
    try:
        address = ipaddress.ip_address(bind)
    except ValueError as exc:
        raise ValueError("bind must be a numeric loopback or RFC1918 address") from exc
    if address.is_loopback:
        return
    if address.version != 4 or not any(address in network for network in LAN_NETWORKS):
        raise ValueError("public, wildcard and non-RFC1918 bind addresses are not allowed")
    if not allow_lan:
        raise ValueError("RFC1918 bind requires allow_lan=true")


# ai-generated: load settings only when every security-relevant JSON type is exact.
def load_settings(path: Path) -> Settings:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("settings must be a JSON object")
    bind = payload.get("bind", "127.0.0.1")
    port = payload.get("port", 8091)
    allow_lan = payload.get("allow_lan", False)
    username = payload.get("username", "admin")
    password_hash = payload.get("password_hash", "")
    if not isinstance(bind, str):
        raise ValueError("bind must be a string")
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("port must be an integer")
    if not isinstance(allow_lan, bool):
        raise ValueError("allow_lan must be a boolean")
    if not isinstance(username, str) or not isinstance(password_hash, str):
        raise ValueError("username and password_hash must be strings")
    settings = Settings(
        bind=bind,
        port=port,
        allow_lan=allow_lan,
        username=username,
        password_hash=password_hash,
        client_service=str(payload.get("client_service", "/opt/etc/init.d/S96olcrtc-native")),
        doctor=str(payload.get("doctor", "/opt/lib/olcrtc-keenetic/doctor.sh")),
        config_helper=str(payload.get("config_helper", "/opt/lib/olcrtc-keenetic/import-uri.sh")),
        client_config=str(payload.get("client_config", "/opt/etc/olcrtc-keenetic/client.yaml")),
        config_path=str(path),
    )
    validate_bind_address(settings.bind, settings.allow_lan)
    if not 1 <= settings.port <= 65535:
        raise ValueError("port is out of range")
    if not settings.username or not settings.password_hash:
        raise ValueError("username and password_hash are required")
    return settings


# ai-generated: initialize a new settings file without exposing the password.
def initialize_settings(
    path: Path, bind: str, port: int, allow_lan: bool, password_file: Path | None = None
) -> None:
    if path.exists():
        raise FileExistsError(f"settings already exist: {path}")
    validate_bind_address(bind, allow_lan)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port is out of range")
    if password_file is None:
        password = getpass.getpass("New web password (minimum 12 characters): ")
        confirm = getpass.getpass("Repeat web password: ")
        if not hmac.compare_digest(password, confirm):
            raise ValueError("passwords do not match")
    else:
        if password_file.stat().st_size > 4096:
            raise ValueError("password file is too large")
        password = password_file.read_text(encoding="utf-8").rstrip("\r\n")
    payload = {
        "bind": bind,
        "port": port,
        "allow_lan": allow_lan,
        "username": "admin",
        "password_hash": hash_password(password),
        "client_service": "/opt/etc/init.d/S96olcrtc-native",
        "doctor": "/opt/lib/olcrtc-keenetic/doctor.sh",
        "config_helper": "/opt/lib/olcrtc-keenetic/import-uri.sh",
        "client_config": "/opt/etc/olcrtc-keenetic/client.yaml",
    }
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
        output.write("\n")


# ai-generated: parse command-line arguments.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="olcRTC Keenetic web control plane")
    parser.add_argument("--config", default="/opt/etc/olcrtc-keenetic/web.json")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--bind", default="127.0.0.1")
    init_parser.add_argument("--port", type=int, default=8091)
    init_parser.add_argument("--allow-lan", action="store_true")
    init_parser.add_argument("--password-file", type=Path)
    subparsers.add_parser("run")
    return parser.parse_args()


# ai-generated: initialize settings or run the threaded web service.
def main() -> int:
    arguments = parse_args()
    path = Path(arguments.config)
    try:
        if arguments.command == "init":
            initialize_settings(
                path, arguments.bind, arguments.port, arguments.allow_lan, arguments.password_file
            )
            print(f"settings created: {path}")
            return 0
        settings = load_settings(path)
        server = ControlServer((settings.bind, settings.port), ControlState(settings))
        print(f"olcRTC web UI listening on http://{settings.bind}:{settings.port}")
        server.serve_forever(poll_interval=0.5)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"olcrtc-web: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


INDEX_HTML = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>olcRTC</title><style>
:root{color-scheme:dark;--bg:#09090f;--card:#12121b;--card2:#191927;--line:#2d2a3d;--strong:#4c3f72;--text:#f7f8f8;--muted:#8a8f98;--ok:#22c55e;--bad:#f97316;--accent:#7c3aed;--accent2:#8b5cf6}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}main{max-width:1020px;margin:auto;padding:24px}.top{display:flex;align-items:center;justify-content:space-between;gap:12px}h1{font-size:25px}h2{font-size:19px}.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}.card:hover{border-color:var(--strong)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}button,input,select{font:inherit;border-radius:9px;border:1px solid var(--strong);padding:10px 12px;min-height:42px}button{background:var(--card2);color:var(--text);cursor:pointer}button:hover{border-color:var(--accent2)}button.primary{background:var(--accent);border-color:var(--accent);color:white;font-weight:700}button.danger{background:transparent;border-color:var(--bad);color:#fdba74}input,select{width:100%;background:var(--card2);color:var(--text)}input:focus,select:focus{outline:3px solid rgba(124,58,237,.25);border-color:var(--accent)}label{display:grid;gap:6px;color:var(--muted)}pre{white-space:pre-wrap;word-break:break-word;max-height:360px;overflow:auto;color:#d0d6e0;background:#0c0c14;border-radius:10px;padding:12px}.muted{color:var(--muted)}.hidden{display:none}.ok{color:var(--ok)}.bad{color:var(--bad)}.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1;min-width:110px}@media(max-width:650px){main{padding:12px}.top{align-items:flex-start}}
</style></head><body><main><div class="top"><h1>olcRTC</h1><button id="logout" class="hidden">Выйти</button></div>
<section id="login" class="card"><h2>Вход</h2><div class="grid"><input id="user" value="admin" autocomplete="username"><input id="pass" type="password" placeholder="Пароль" autocomplete="current-password"></div><p><button id="loginBtn" class="primary">Войти</button> <span id="loginMsg" class="bad"></span></p></section>
<div id="app" class="hidden"><section class="card"><div class="top"><h2>Состояние</h2><button id="refresh">Обновить</button></div><p id="health" class="muted">Проверка...</p><pre id="status"></pre><div class="row"><button data-action="start">Запустить</button><button data-action="restart">Перезапустить</button><button data-action="stop">Остановить</button><button data-action="probe">Проверить SOCKS</button><button data-action="diagnostics">Диагностика</button></div></section>
<section class="card"><h2>Подключение</h2><p class="muted">Принимается только canonical olcrtc:// URI. Секрет не показывается повторно.</p><input id="uri" type="password" placeholder="olcrtc://..."><p><button id="importBtn" class="primary">Проверить и применить</button> <span id="importMsg"></span></p></section>
<section class="card"><h2>Параметры клиента</h2><div class="grid"><label>Provider<select id="provider"><option>jitsi</option><option>telemost</option><option>wbstream</option></select></label><label>Transport<select id="transport"><option>datachannel</option><option>vp8channel</option><option>seichannel</option><option>videochannel</option></select></label><label>Комната<input id="room" placeholder="https://meet.example/room"></label></div><p><button id="loadProfile">Загрузить</button> <button id="saveProfile" class="primary">Сохранить</button> <span id="profileMsg"></span></p><p class="muted">Расширенные параметры transport сохраняются при импорте URI. Форма меняет основные совместимые поля, не показывая ключ.</p></section>
<section class="card"><h2>Миграция и обновление</h2><p class="muted">Если старый клиент занимает SOCKS-порт, используйте «Переключить». При ошибке старая служба запускается обратно. Удаление доступно только после успешного переключения и создаёт локальную копию.</p><div class="row"><button data-action="enable-native">Включить новый</button><button data-action="cutover" class="primary">Переключить со старого</button><button data-action="legacy-rollback">Вернуть старый</button><button data-action="update">Обновить</button><button data-action="binary-rollback">Откатить бинарник</button><button data-action="purge-legacy" class="danger">Удалить старый клиент</button></div></section>
<section class="card"><h2>Безопасность панели</h2><div class="grid"><label>Новый логин<input id="newUser" value="admin" autocomplete="username"></label><label>Новый пароль<input id="newPass" type="password" minlength="12" autocomplete="new-password"></label><label>Повторите пароль<input id="newConfirm" type="password" minlength="12" autocomplete="new-password"></label></div><p><button id="credentialsBtn" class="primary">Сменить логин и пароль</button> <span id="credentialsMsg"></span></p><p class="muted">После смены все активные сессии будут завершены.</p></section>
<section class="card"><div class="top"><h2>Журнал</h2><button id="logsBtn">Обновить</button></div><pre id="logs"></pre></section></div>
<script>
let csrf='';const q=s=>document.querySelector(s);async function api(path,options={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const j=await r.json();if(!r.ok)throw new Error(j.error||'request_failed');return j}async function session(){const s=await api('/api/session');if(s.authenticated){csrf=s.csrf;q('#login').classList.add('hidden');q('#app').classList.remove('hidden');q('#logout').classList.remove('hidden');await refresh()}}async function refresh(){const j=await api('/api/status');q('#health').textContent=j.ok?'Туннель готов':'Требуется внимание';q('#health').className=j.ok?'ok':'bad';q('#status').textContent=JSON.stringify(j,null,2)}async function loadProfile(){try{const j=await api('/api/profile');if(!j.ok||!j.profile)throw new Error(j.output||'Сначала импортируйте URI');q('#provider').value=j.profile.provider;q('#transport').value=j.profile.transport;q('#room').value=j.profile.room;q('#profileMsg').textContent='Загружено'}catch(e){q('#profileMsg').textContent=e.message}}q('#loginBtn').onclick=async()=>{try{const j=await api('/api/login',{method:'POST',body:JSON.stringify({username:q('#user').value,password:q('#pass').value})});csrf=j.csrf;q('#pass').value='';await session()}catch(e){q('#loginMsg').textContent=e.message}};q('#refresh').onclick=refresh;q('#logsBtn').onclick=async()=>{const j=await api('/api/logs');q('#logs').textContent=j.output};document.querySelectorAll('[data-action]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{if(b.dataset.action==='purge-legacy'&&!confirm('Удалить старый клиент после создания резервной копии?'))return;const j=await api('/api/action',{method:'POST',body:JSON.stringify({csrf,action:b.dataset.action})});q('#status').textContent=j.output;await refresh()}catch(e){q('#status').textContent=e.message}finally{b.disabled=false}});q('#importBtn').onclick=async()=>{try{const j=await api('/api/import-uri',{method:'POST',body:JSON.stringify({csrf,uri:q('#uri').value})});q('#uri').value='';q('#importMsg').textContent=j.output||'Применено';await loadProfile();await refresh()}catch(e){q('#importMsg').textContent=e.message}};q('#loadProfile').onclick=loadProfile;q('#saveProfile').onclick=async()=>{try{const current=await api('/api/profile');const selected=q('#transport').value;const parameters=current.profile&&current.profile.transport===selected&&current.profile.parameters?current.profile.parameters:{};const profile={provider:q('#provider').value,transport:selected,room:q('#room').value,parameters};const j=await api('/api/settings',{method:'POST',body:JSON.stringify({csrf,profile})});q('#profileMsg').textContent=j.output||'Сохранено'}catch(e){q('#profileMsg').textContent=e.message}};q('#credentialsBtn').onclick=async()=>{try{await api('/api/change-credentials',{method:'POST',body:JSON.stringify({csrf,username:q('#newUser').value,password:q('#newPass').value,confirmation:q('#newConfirm').value})});location.reload()}catch(e){q('#credentialsMsg').textContent=e.message}};q('#logout').onclick=async()=>{await api('/api/logout',{method:'POST',body:JSON.stringify({csrf})});location.reload()};session();
</script></main></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())

