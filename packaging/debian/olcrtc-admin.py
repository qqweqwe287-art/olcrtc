#!/usr/bin/env python3
"""Local administration UI for olcRTC Debian server instances."""

# ai-generated: localhost-only, authenticated administration UI for Debian packaging.

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import ssl
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


CONFIG_DIR = Path("/etc/olcrtc-native")
LIB_DIR = Path("/usr/local/lib/olcrtc-native")
STATE_DIR = Path("/var/lib/olcrtc-native")
BACKUP_DIR = STATE_DIR / "backups"
CREDENTIAL_PATH = CONFIG_DIR / "admin.credentials"
INSTALLER = Path("/usr/local/sbin/olcrtc-native-install-server")
UNIT_PREFIX = "olcrtc-native@"
MANAGED_HEADER = "# Managed by olcRTC local admin UI."
INSTANCE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
DNS_RE = re.compile(r"[^\s:]+:\d{1,5}")
RELEASE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
PROVIDERS = {"jitsi", "telemost", "wbstream"}
TRANSPORTS = {"datachannel", "vp8channel", "seichannel", "videochannel"}
CSRF_TOKEN = secrets.token_urlsafe(32)
QR_VALUES: dict[str, str] = {}
LEGACY_SERVICES = ("olcrtc-server.service", "olcrtc-admin.service")
LEGACY_PATHS = (
    Path("/etc/systemd/system/olcrtc-server.service"),
    Path("/etc/systemd/system/olcrtc-server@.service"),
    Path("/etc/systemd/system/olcrtc-admin.service"),
    Path("/usr/local/bin/olcrtc"),
    Path("/usr/local/bin/olcrtc-admin"),
    Path("/usr/local/bin/olcrtc-launcher"),
    Path("/usr/local/lib/olcrtc"),
    Path("/etc/olcrtc"),
    Path("/var/lib/olcrtc"),
)


# ai-generated: run a fixed local command without a shell and return safe text.
def command(*arguments: str, timeout: int = 20) -> tuple[int, str]:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return result.returncode, result.stdout


# ai-generated: replace secrets and credential-like values before UI rendering.
def redact(value: str) -> str:
    value = re.sub(r"\b[0-9a-fA-F]{64}\b", "[redacted-key]", value)
    value = re.sub(r"(?i)(token|password|pass|secret|key)\s*[:=]\s*[^\s,]+", r"\1=[redacted]", value)
    return value


# ai-generated: return a systemd-safe service instance name or raise ValueError.
def instance_name(value: str) -> str:
    if not INSTANCE_RE.fullmatch(value) or value in {".", ".."} or ".." in value:
        raise ValueError("invalid instance name")
    return value


# ai-generated: validate values accepted by the narrow generated server YAML schema.
def config_values(values: dict[str, str]) -> dict[str, str]:
    instance = instance_name(values.get("instance", ""))
    provider = values.get("provider", "")
    transport = values.get("transport", "")
    room = values.get("room", "")
    dns = values.get("dns", "")
    if provider not in PROVIDERS:
        raise ValueError("unknown provider")
    if transport not in TRANSPORTS:
        raise ValueError("unknown transport")
    if not room or len(room) > 512 or any(character.isspace() for character in room) or room == "any":
        raise ValueError("room must be a non-empty room ID or URL, not 'any'")
    if not DNS_RE.fullmatch(dns) or int(dns.rsplit(":", 1)[1]) > 65535:
        raise ValueError("DNS must use host:port")
    if provider == "jitsi":
        parsed = urlparse(room)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path in {"", "/"}:
            raise ValueError("Jitsi room must be a complete https://host/room URL")
    if provider == "wbstream" and transport == "datachannel":
        raise ValueError("wbstream/datachannel requires an account token and is unavailable in this safe UI")
    return {"instance": instance, "provider": provider, "transport": transport, "room": room, "dns": dns}


# ai-generated: quote a scalar through JSON-compatible YAML double-quoted syntax.
def yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + "\""


# ai-generated: build the complete restricted server YAML managed by the UI.
def config_text(values: dict[str, str]) -> str:
    return "\n".join(
        (
            MANAGED_HEADER,
            "mode: srv",
            "auth:",
            f"  provider: {values['provider']}",
            "room:",
            f"  id: {yaml_string(values['room'])}",
            "crypto:",
            f"  key_file: ./{values['instance']}.key",
            "net:",
            f"  transport: {values['transport']}",
            f"  dns: {yaml_string(values['dns'])}",
            "liveness:",
            "  interval: 10s",
            "  timeout: 15s",
            "  failures: 4",
            "lifecycle:",
            "  max_session_duration: 6h",
            "debug: false",
            "",
        )
    )


# ai-generated: parse only UI-owned YAML so foreign configurations are never modified.
def managed_config(instance: str) -> dict[str, str] | None:
    path = CONFIG_DIR / f"{instance}.yaml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0] != MANAGED_HEADER:
        return None
    found: dict[str, str] = {"instance": instance}
    expressions = {
        "provider": r"^  provider: ([a-z]+)$",
        "room": r'^  id: "(.*)"$',
        "transport": r"^  transport: ([a-z]+)$",
        "dns": r'^  dns: "(.*)"$',
    }
    for name, expression in expressions.items():
        for line in lines:
            match = re.match(expression, line)
            if match:
                found[name] = match.group(1).replace('\\"', '"').replace("\\\\", "\\")
                break
    try:
        return config_values(found)
    except ValueError:
        return None


# ai-generated: create the documented Spec URI and mask its key unless explicitly revealed.
def spec_uri(instance: str, reveal: bool) -> str:
    values = managed_config(instance)
    if values is None:
        raise ValueError("the UI can generate a URI only for its managed configuration")
    key = "[hidden]"
    if reveal:
        try:
            key = (CONFIG_DIR / f"{instance}.key").read_text(encoding="ascii").strip()
        except OSError as exc:
            raise ValueError(f"key is unavailable: {exc}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("key file is invalid")
    return f"olcrtc://{values['provider']}?{values['transport']}@{values['room']}#{key}$olcrtc"


# ai-generated: render one short-lived URI as a bounded PNG without a shell.
def qr_png(uri: str) -> bytes:
    try:
        result = subprocess.run(
            ("qrencode", "-t", "PNG", "-o", "-", "-s", "6", "--", uri),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"QR generation failed: {exc}") from exc
    if result.returncode != 0 or not result.stdout.startswith(b"\x89PNG") or len(result.stdout) > 1024 * 1024:
        raise ValueError("QR generation failed")
    return result.stdout


# ai-generated: atomically write a root-owned configuration file without following a final symlink.
def atomic_write(path: Path, contents: str, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


# ai-generated: copy one regular file into a package-owned timestamped backup.
def backup_instance(instance: str, reason: str) -> Path:
    name = instance_name(instance)
    if not re.fullmatch(r"[a-z-]{3,32}", reason):
        raise ValueError("invalid backup reason")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
    destination = BACKUP_DIR / f"{name}-{reason}-{stamp}"
    destination.mkdir(parents=True, mode=0o700)
    copied: list[str] = []
    for suffix in (".yaml", ".key"):
        source = CONFIG_DIR / f"{name}{suffix}"
        if source.is_file() and not source.is_symlink():
            shutil.copy2(source, destination / source.name, follow_symlinks=False)
            os.chmod(destination / source.name, 0o600)
            copied.append(source.name)
    atomic_write(
        destination / "backup.json",
        json.dumps({"schema": 1, "instance": name, "reason": reason, "files": copied}, ensure_ascii=False, indent=2) + "\n",
        0o600,
    )
    return destination


# ai-generated: restore the two fixed instance files from a verified local backup.
def restore_instance(instance: str, backup: Path) -> None:
    name = instance_name(instance)
    if backup.parent != BACKUP_DIR or not backup.is_dir() or backup.is_symlink():
        raise ValueError("invalid backup directory")
    for suffix in (".yaml", ".key"):
        saved = backup / f"{name}{suffix}"
        target = CONFIG_DIR / f"{name}{suffix}"
        if saved.is_file() and not saved.is_symlink():
            atomic_write(target, saved.read_text(encoding="utf-8"), 0o640)
        elif target.exists() and not target.is_symlink():
            target.unlink()


# ai-generated: report exact legacy Manager artifacts without exposing their contents.
def legacy_report() -> list[str]:
    return [str(path) for path in LEGACY_PATHS if path.exists() or path.is_symlink()]


# ai-generated: preserve exact legacy paths before any destructive migration action.
def backup_legacy() -> Path:
    found = legacy_report()
    if not found:
        raise ValueError("старая установка Manager не найдена")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3)
    destination = BACKUP_DIR / f"legacy-manager-{stamp}"
    payload = destination / "root"
    payload.mkdir(parents=True, mode=0o700)
    copied: list[str] = []
    for source in LEGACY_PATHS:
        if not (source.exists() or source.is_symlink()):
            continue
        relative = Path(*source.parts[1:])
        target = payload / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        elif source.is_dir():
            shutil.copytree(source, target, symlinks=True)
        elif source.is_file():
            shutil.copy2(source, target, follow_symlinks=False)
        copied.append(str(source))
    atomic_write(
        destination / "backup.json",
        json.dumps({"schema": 1, "kind": "legacy-manager", "paths": copied}, ensure_ascii=False, indent=2) + "\n",
        0o600,
    )
    return destination


# ai-generated: remove only the documented old Manager paths after a backup.
def purge_legacy() -> Path:
    backup = backup_legacy()
    for service in LEGACY_SERVICES:
        command("systemctl", "disable", "--now", service, timeout=30)
    for path in LEGACY_PATHS:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)
    command("systemctl", "daemon-reload", timeout=15)
    return backup


# ai-generated: create or rotate one binary 32-byte key without exposing it in the browser.
def ensure_key(instance: str, rotate: bool) -> None:
    path = CONFIG_DIR / f"{instance}.key"
    if path.exists() and not rotate:
        return
    atomic_write(path, secrets.token_hex(32) + "\n", 0o640)
    try:
        import grp

        os.chown(path, 0, grp.getgrnam("olcrtc-native").gr_gid)
    except (ImportError, KeyError):
        pass


# ai-generated: collect unit state via fixed systemctl arguments.
def unit_state(instance: str) -> tuple[str, str]:
    unit = f"{UNIT_PREFIX}{instance}.service"
    _, active = command("systemctl", "is-active", unit, timeout=5)
    _, enabled = command("systemctl", "is-enabled", unit, timeout=5)
    return active.strip(), enabled.strip()


# ai-generated: enumerate regular YAML configs and their non-secret status.
def instances() -> list[tuple[str, str, str, bool]]:
    result: list[tuple[str, str, str, bool]] = []
    for path in sorted(CONFIG_DIR.glob("*.yaml")):
        if path.is_symlink():
            continue
        try:
            name = instance_name(path.stem)
        except ValueError:
            continue
        active, enabled = unit_state(name)
        result.append((name, active, enabled, managed_config(name) is not None))
    return result


# ai-generated: authenticate the local operator using the root-readable generated credential.
def authorized(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:], validate=True).decode("utf-8")
        username, password = raw.split(":", 1)
        expected = CREDENTIAL_PATH.read_text(encoding="utf-8").strip().split(":", 1)
    except (OSError, ValueError, UnicodeDecodeError):
        return False
    return len(expected) == 2 and hmac.compare_digest(username, expected[0]) and verify_password(password, expected[1])


# ai-generated: HTTP handler limited to local authenticated administration actions.
class Handler(BaseHTTPRequestHandler):
    server_version = "olcRTC-admin/1"

    def log_message(self, _format: str, *_arguments: object) -> None:
        return

    def authenticate(self) -> bool:
        if authorized(self.headers.get("Authorization")):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="olcRTC local admin", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def send_html(self, title: str, body: str, status: int = 200) -> None:
        page = f"""<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title><style>
:root{{color-scheme:dark;--bg:#09090f;--surface:#12121b;--surface2:#191927;--line:#2d2a3d;--strong:#4c3f72;--text:#f7f8f8;--muted:#8a8f98;--accent:#7c3aed;--accent2:#8b5cf6;--good:#22c55e;--bad:#f97316}}*{{box-sizing:border-box}}body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1240px;margin:0 auto;padding:24px;background:var(--bg);color:var(--text);line-height:1.5}}nav{{position:sticky;top:12px;z-index:3;display:flex;gap:14px;align-items:center;flex-wrap:wrap;padding:14px 18px;border:1px solid var(--line);border-radius:14px;background:rgba(18,18,27,.94);backdrop-filter:blur(12px)}}nav strong{{font-size:19px;margin-right:auto}}a{{color:#c4b5fd;text-decoration:none}}a:hover{{color:#fff}}h1{{font-size:30px;margin:28px 0 18px}}h2{{margin-top:28px}}.card,table,pre{{background:var(--surface);border:1px solid var(--line);border-radius:14px}}.card{{padding:18px;margin:14px 0}}input,select,button{{margin:.3rem;padding:.7rem .85rem;border:1px solid var(--strong);border-radius:9px;background:var(--surface2);color:var(--text);min-height:42px}}input:focus,select:focus{{outline:3px solid rgba(124,58,237,.25);border-color:var(--accent)}}button{{cursor:pointer;background:var(--accent);border-color:var(--accent);font-weight:700}}button:hover{{background:var(--accent2)}}button.danger{{background:transparent;border-color:var(--bad);color:#fdba74}}button.secondary{{background:var(--surface2);border-color:var(--line)}}form{{margin:.45rem 0}}label{{display:inline-flex;gap:6px;align-items:center;flex-wrap:wrap;margin:.25rem}}table{{border-collapse:separate;border-spacing:0;width:100%;overflow:hidden}}td,th{{padding:.85rem;border-bottom:1px solid var(--line);text-align:left}}tr:last-child td{{border-bottom:0}}pre{{white-space:pre-wrap;padding:1rem;overflow:auto}}.warn{{color:#fbbf24}}.ok{{color:#4ade80}}.bad{{color:#fb923c}}.muted{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}}code{{color:#ddd6fe}}@media(max-width:700px){{body{{padding:12px}}table{{display:block;overflow-x:auto}}nav{{top:4px}}}}
</style><body><nav><strong>◈ olcRTC Admin</strong><a href=/>Инстансы</a><a href=/diagnostics>Диагностика</a><a href=/backups>Копии</a><a href=/legacy>Старый Manager</a><a href=/update>Обновление</a><a href=/security>Безопасность</a></nav><h1>{html.escape(title)}</h1>{body}</body></html>"""
        encoded = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'self'")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def form(self, values: dict[str, str] | None = None, warning: str = "") -> str:
        values = values or {"instance": "main", "provider": "jitsi", "transport": "datachannel", "room": "", "dns": "8.8.8.8:53"}
        def field(name: str) -> str:
            return html.escape(values.get(name, ""), quote=True)
        provider_options = "".join(f'<option value="{name}"{" selected" if values.get("provider") == name else ""}>{name}</option>' for name in sorted(PROVIDERS))
        transport_options = "".join(f'<option value="{name}"{" selected" if values.get("transport") == name else ""}>{name}</option>' for name in sorted(TRANSPORTS))
        return f'''<p class=warn>{html.escape(warning)}</p><form method=post action=/save><input type=hidden name=csrf value="{CSRF_TOKEN}"><label>Инстанс <input required pattern="[A-Za-z0-9][A-Za-z0-9_.-]{{0,63}}" name=instance value="{field('instance')}"></label><label>Provider <select name=provider>{provider_options}</select></label><label>Transport <select name=transport>{transport_options}</select></label><label>Комната / URL <input required name=room size=46 value="{field('room')}"></label><label>DNS <input required name=dns value="{field('dns')}"></label><label><input type=checkbox name=rotate_key> Создать новый ключ (старый ключ перестанет работать)</label><button>Сохранить валидную конфигурацию</button></form><p>Ключ создаётся на VPS в <code>/etc/olcrtc-native/&lt;instance&gt;.key</code> и в браузер не выводится.</p>'''

    def do_GET(self) -> None:
        if not self.authenticate():
            return
        route = urlparse(self.path).path
        if route == "/qr":
            token = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            uri = QR_VALUES.pop(token, None)
            if uri is None:
                self.send_html("QR недоступен", "<p>Ссылка истекла или уже использована.</p>", 404)
                return
            try:
                encoded = qr_png(uri)
            except ValueError as exc:
                self.send_html("QR недоступен", f"<p>{html.escape(str(exc))}</p>", 500)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        if route == "/":
            rows = "".join(f"<tr><td><strong>{html.escape(name)}</strong></td><td>{html.escape(active)}</td><td>{html.escape(enabled)}</td><td>{'Управляется UI' if owned else 'Внешний YAML'}</td><td><a href='/edit?instance={html.escape(name, quote=True)}'>Настройки</a> · <a href='/uri?instance={html.escape(name, quote=True)}'>URI</a> · <a href='/logs?instance={html.escape(name, quote=True)}'>Журнал</a>{self.actions(name)}</td></tr>" for name, active, enabled, owned in instances())
            empty = "<p class=muted>Инстансов пока нет. Создайте первый ниже.</p>" if not rows else ""
            self.send_html("Инстансы", f"<div class=card><p>Серверные подключения и их фактическое состояние.</p>{empty}<table><tr><th>Имя</th><th>Состояние</th><th>Автозапуск</th><th>Конфиг</th><th>Управление</th></tr>{rows}</table></div><h2>Новый инстанс</h2><div class=card>{self.form()}</div>")
            return
        if route == "/edit":
            try:
                name = instance_name(parse_qs(urlparse(self.path).query).get("instance", [""])[0])
            except ValueError:
                self.send_html("Ошибка", "<p>Некорректный инстанс.</p>", 400)
                return
            values = managed_config(name)
            if values is None:
                self.send_html("Внешняя конфигурация", "<p>Этот YAML создан вне панели. Он доступен для запуска и журналов, но не редактируется UI.</p>", 409)
                return
            self.send_html(f"Изменение {name}", self.form(values))
            return
        if route == "/logs":
            try:
                name = instance_name(parse_qs(urlparse(self.path).query).get("instance", [""])[0])
            except ValueError:
                self.send_html("Ошибка", "<p>Некорректный инстанс.</p>", 400)
                return
            _, output = command("journalctl", "-u", f"{UNIT_PREFIX}{name}.service", "-n", "200", "--no-pager", "-o", "short-iso", timeout=10)
            self.send_html(f"Журнал {name}", f"<pre>{html.escape(redact(output))}</pre>")
            return
        if route == "/uri":
            try:
                name = instance_name(parse_qs(urlparse(self.path).query).get("instance", [""])[0])
                uri = spec_uri(name, False)
            except ValueError as exc:
                self.send_html("URI недоступен", f"<p>{html.escape(str(exc))}</p>", 409)
                return
            self.send_html(f"Spec URI {name}", f"<p>Секрет по умолчанию скрыт и QR-код не формируется.</p><pre>{html.escape(uri)}</pre><form method=post action=/reveal-uri><input type=hidden name=csrf value=\"{CSRF_TOKEN}\"><input type=hidden name=instance value=\"{html.escape(name, quote=True)}\"><label><input required type=checkbox name=acknowledge> Я понимаю, что ключ будет показан на экране</label><button>Показать URI и QR</button></form>")
            return
        if route == "/diagnostics":
            _, system = command("systemctl", "is-system-running", timeout=5)
            binary = LIB_DIR / "current" / "olcrtc"
            manifest = LIB_DIR / "current" / "manifest.tsv"
            code, failed = command("systemctl", "--failed", "--no-pager", "--plain", timeout=10)
            disk = shutil.disk_usage(STATE_DIR if STATE_DIR.exists() else Path("/"))
            details = f"systemd: {system.strip()}\nбинарник: {'есть' if binary.is_file() else 'не найден'}\nmanifest: {'есть' if manifest.is_file() else 'не найден'}\nинстансов: {len(instances())}\nсвободно: {disk.free // 1024 // 1024} MiB\nстарый Manager: {len(legacy_report())} объектов\n\nfailed units (code={code}):\n{redact(failed)}"
            self.send_html("Диагностика", f"<div class=card><p>Отчёт не содержит ключи и пароли.</p><pre>{html.escape(details)}</pre></div>")
            return
        if route == "/backups":
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            items = []
            for path in sorted(BACKUP_DIR.iterdir(), reverse=True):
                if path.is_dir() and not path.is_symlink():
                    items.append(f"<li><code>{html.escape(path.name)}</code></li>")
            listing = "".join(items) or "<li>Резервных копий пока нет.</li>"
            self.send_html("Резервные копии", f"<div class=card><p>Копии хранятся локально в <code>{html.escape(str(BACKUP_DIR))}</code> с правами root.</p><ul>{listing}</ul></div>")
            return
        if route == "/legacy":
            found = legacy_report()
            listing = "".join(f"<li><code>{html.escape(path)}</code></li>" for path in found) or "<li>Старая установка не найдена.</li>"
            purge = ""
            if found:
                purge = f'''<form method=post action=/purge-legacy><input type=hidden name=csrf value="{CSRF_TOKEN}"><label>Введите <code>УДАЛИТЬ СТАРЫЙ MANAGER</code><input required name=confirmation></label><button class=danger>Создать копию и удалить старый Manager</button></form>'''
            self.send_html("Старый Manager", f"<div class=card><p>Найдены только перечисленные объекты. Новый продукт их не использует.</p><ul>{listing}</ul>{purge}<p class=warn>Удаление не затрагивает <code>/etc/olcrtc-native</code> и сначала создаёт резервную копию.</p></div>")
            return
        if route == "/update":
            self.send_html("Обновление", f"<form method=post action=/update><input type=hidden name=csrf value=\"{CSRF_TOKEN}\"><label>Тег выпуска (пусто = latest) <input name=release></label><button>Скачать и применить</button></form><p>Активные инстансы перезапустятся. Конфигурации не заменяются.</p>")
            return
        if route == "/security":
            self.send_html("Безопасность", f"<form method=post action=/change-credentials><input type=hidden name=csrf value=\"{CSRF_TOKEN}\"><label>Новый логин <input required name=username value=admin></label><label>Новый пароль <input required minlength=12 type=password name=password></label><label>Повторите пароль <input required minlength=12 type=password name=confirm></label><button>Сменить данные входа</button></form><p class=warn>После сохранения браузер запросит новые данные.</p>")
            return
        self.send_html("Не найдено", "<p>Страница не найдена.</p>", 404)

    def do_POST(self) -> None:
        if not self.authenticate():
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 16384 or self.headers.get("Content-Type", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
            self.send_html("Ошибка", "<p>Некорректная форма.</p>", 400)
            return
        values = {key: item[-1] for key, item in parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True).items()}
        if not hmac.compare_digest(values.pop("csrf", ""), CSRF_TOKEN):
            self.send_html("Ошибка", "<p>Недействительная защита формы. Обновите страницу.</p>", 403)
            return
        route = urlparse(self.path).path
        if route == "/save":
            backup: Path | None = None
            was_active = False
            try:
                config = config_values(values)
                CONFIG_DIR.mkdir(mode=0o750, parents=True, exist_ok=True)
                path = CONFIG_DIR / f"{config['instance']}.yaml"
                if path.is_symlink():
                    raise ValueError("refusing symbolic-link configuration")
                was_active = unit_state(config["instance"])[0] == "active"
                backup = backup_instance(config["instance"], "before-save")
                atomic_write(path, config_text(config), 0o640)
                import grp
                os.chown(path, 0, grp.getgrnam("olcrtc-native").gr_gid)
                ensure_key(config["instance"], values.get("rotate_key") == "on")
                if was_active:
                    code, output = command("systemctl", "restart", f"{UNIT_PREFIX}{config['instance']}.service", timeout=30)
                    if code != 0 or unit_state(config["instance"])[0] != "active":
                        if backup is not None:
                            restore_instance(config["instance"], backup)
                            command("systemctl", "restart", f"{UNIT_PREFIX}{config['instance']}.service", timeout=30)
                        raise ValueError("новая конфигурация не запустилась; предыдущая восстановлена: " + redact(output))
            except (OSError, ValueError) as exc:
                self.send_html("Конфигурация не сохранена", self.form(values, str(exc)), 400)
                return
            self.send_html("Конфигурация сохранена", f"<p class=ok>{html.escape(config['instance'])}: YAML записан. Ключ не показан.</p>{self.actions(config['instance'])}")
            return
        if route == "/action":
            try:
                name = instance_name(values.get("instance", ""))
                action = values.get("action", "")
                if action not in {"start", "stop", "restart", "enable", "disable"}:
                    raise ValueError("unknown action")
                code, output = command("systemctl", action, f"{UNIT_PREFIX}{name}.service", timeout=30)
            except ValueError as exc:
                self.send_html("Ошибка", f"<p>{html.escape(str(exc))}</p>", 400)
                return
            self.send_html("Операция службы", f"<p>{html.escape(action)}: {'готово' if code == 0 else 'ошибка'}</p><pre>{html.escape(redact(output))}</pre>{self.actions(name)}")
            return
        if route == "/clone":
            try:
                source = instance_name(values.get("source", ""))
                destination = instance_name(values.get("destination", ""))
                current = managed_config(source)
                if current is None:
                    raise ValueError("клонировать можно только конфигурацию, управляемую UI")
                target = CONFIG_DIR / f"{destination}.yaml"
                if target.exists() or target.is_symlink():
                    raise ValueError("инстанс с таким именем уже существует")
                current["instance"] = destination
                atomic_write(target, config_text(current), 0o640)
                ensure_key(destination, True)
            except (OSError, ValueError) as exc:
                self.send_html("Клонирование не выполнено", f"<p class=bad>{html.escape(str(exc))}</p>", 400)
                return
            self.send_html("Инстанс клонирован", f"<p class=ok>{html.escape(source)} → {html.escape(destination)}. Создан новый ключ.</p>{self.actions(destination)}")
            return
        if route == "/delete":
            try:
                name = instance_name(values.get("instance", ""))
                if values.get("confirmation") != name:
                    raise ValueError("для удаления введите точное имя инстанса")
                backup = backup_instance(name, "before-delete")
                command("systemctl", "disable", "--now", f"{UNIT_PREFIX}{name}.service", timeout=30)
                for suffix in (".yaml", ".key"):
                    target = CONFIG_DIR / f"{name}{suffix}"
                    if target.is_symlink():
                        raise ValueError("отказ удаления символической ссылки")
                    target.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                self.send_html("Удаление не выполнено", f"<p class=bad>{html.escape(str(exc))}</p>", 400)
                return
            self.send_html("Инстанс удалён", f"<p class=ok>Инстанс удалён. Копия: <code>{html.escape(str(backup))}</code>.</p>")
            return
        if route == "/purge-legacy":
            if values.get("confirmation") != "УДАЛИТЬ СТАРЫЙ MANAGER":
                self.send_html("Удаление отменено", "<p class=bad>Контрольная фраза не совпала.</p>", 400)
                return
            try:
                backup = purge_legacy()
            except (OSError, ValueError) as exc:
                self.send_html("Старый Manager не удалён", f"<p class=bad>{html.escape(str(exc))}</p>", 500)
                return
            self.send_html("Старый Manager удалён", f"<p class=ok>Удалены только перечисленные старые пути. Копия: <code>{html.escape(str(backup))}</code>.</p>")
            return
        if route == "/update":
            release = values.get("release", "") or "latest"
            if release != "latest" and not RELEASE_RE.fullmatch(release):
                self.send_html("Ошибка", "<p>Некорректный тег выпуска.</p>", 400)
                return
            code, output = command(str(INSTALLER), "--release", release, timeout=360)
            self.send_html("Обновление", f"<p>{'Выпуск установлен.' if code == 0 else 'Обновление завершилось ошибкой.'}</p><pre>{html.escape(redact(output))}</pre>")
            return
        if route == "/reveal-uri":
            try:
                if values.get("acknowledge") != "on":
                    raise ValueError("подтвердите показ ключа")
                name = instance_name(values.get("instance", ""))
                uri = spec_uri(name, True)
                token = secrets.token_urlsafe(24)
                while len(QR_VALUES) >= 16:
                    QR_VALUES.pop(next(iter(QR_VALUES)))
                QR_VALUES[token] = uri
            except ValueError as exc:
                self.send_html("URI недоступен", f"<p>{html.escape(str(exc))}</p>", 400)
                return
            self.send_html(f"Spec URI {name}", f"<p class=warn>Ключ показан по вашему явному запросу. Не сохраняйте этот экран и не передавайте URI посторонним.</p><pre>{html.escape(uri)}</pre><img width=320 height=320 alt=\"QR-код URI\" src=\"/qr?token={html.escape(token, quote=True)}\">")
            return
        if route == "/change-credentials":
            username = values.get("username", "")
            password = values.get("password", "")
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", username):
                self.send_html("Ошибка", "<p>Логин должен содержать 3-64 безопасных символа.</p>", 400)
                return
            if not hmac.compare_digest(password, values.get("confirm", "")):
                self.send_html("Ошибка", "<p>Пароли не совпадают.</p>", 400)
                return
            try:
                atomic_write(CREDENTIAL_PATH, username + ":" + hash_password(password) + "\n", 0o600)
            except (OSError, ValueError) as exc:
                self.send_html("Ошибка", f"<p>{html.escape(str(exc))}</p>", 400)
                return
            self.send_html("Данные входа изменены", "<p class=ok>Данные сохранены. Закройте вкладку и войдите заново.</p>")
            return
        self.send_html("Не найдено", "<p>Операция не найдена.</p>", 404)

    def actions(self, name: str) -> str:
        escaped = html.escape(name, quote=True)
        forms = "".join(f'<form style="display:inline" method=post action=/action><input type=hidden name=csrf value="{CSRF_TOKEN}"><input type=hidden name=instance value="{escaped}"><input type=hidden name=action value="{action}"><button>{label}</button></form>' for action, label in (("start", "Запустить"), ("stop", "Остановить"), ("restart", "Перезапустить"), ("enable", "Включить"), ("disable", "Выключить")))
        clone = f'<form style="display:inline" method=post action=/clone><input type=hidden name=csrf value="{CSRF_TOKEN}"><input type=hidden name=source value="{escaped}"><input required placeholder="Имя копии" name=destination><button class=secondary>Клонировать</button></form>'
        delete = f'<form style="display:inline" method=post action=/delete><input type=hidden name=csrf value="{CSRF_TOKEN}"><input type=hidden name=instance value="{escaped}"><input required placeholder="Введите {escaped}" name=confirmation><button class=danger>Удалить</button></form>'
        return f"<div>{forms}{clone}{delete}</div>"


# ai-generated: start the loopback-only HTTPS-free administration server behind SSH forwarding.
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--init-credentials", type=Path)
    parser.add_argument("--password-file", type=Path)
    arguments = parser.parse_args()
    if arguments.init_credentials is not None:
        if arguments.password_file is None or arguments.password_file.stat().st_size > 4096:
            parser.error("credential initialization requires a bounded password file")
        password = arguments.password_file.read_text(encoding="utf-8").rstrip("\r\n")
        atomic_write(arguments.init_credentials, "admin:" + hash_password(password) + "\n", 0o600)
        return 0
    if arguments.listen not in {"127.0.0.1", "::1", "0.0.0.0"} or not 1 <= arguments.port <= 65535:
        parser.error("invalid listener or port")
    if arguments.listen == "0.0.0.0" and (arguments.cert is None or arguments.key is None):
        parser.error("a public listener requires TLS certificate and key")
    if (arguments.cert is None) != (arguments.key is None):
        parser.error("TLS certificate and key must be supplied together")
    if not CREDENTIAL_PATH.is_file():
        parser.error(f"missing credentials: {CREDENTIAL_PATH}")
    server = ThreadingHTTPServer((arguments.listen, arguments.port), Handler)
    if arguments.cert is not None and arguments.key is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(arguments.cert, arguments.key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
    return 0


# ai-generated: create a salted memory-hard password verifier.
def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=1 << 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


# ai-generated: verify a password in constant time against the stored scrypt representation.
def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_text, digest_text = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=1 << 14, r=8, p=1, dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


if __name__ == "__main__":
    raise SystemExit(main())

