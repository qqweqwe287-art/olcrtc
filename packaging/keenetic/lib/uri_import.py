#!/usr/bin/env python3
# ai-generated: canonical olcRTC URI importer for the Keenetic package.

"""Import an olcrtc URI into an atomic, secret-safe client configuration."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


URI_PATTERN = re.compile(r"([a-z0-9]+)(?:<(.*)>)?")
HEX_KEY = re.compile(r"[0-9a-fA-F]{64}")
PROVIDERS = {"jitsi", "telemost", "wbstream"}
TRANSPORTS = {"datachannel", "vp8channel", "seichannel", "videochannel"}
PARAMETERS = {
    "datachannel": set(),
    "vp8channel": {"vp8-fps", "vp8-batch"},
    "seichannel": {"fps", "batch", "frag", "ack-ms"},
    "videochannel": {
        "video-w",
        "video-h",
        "video-fps",
        "video-codec",
        "video-qr-size",
        "video-qr-recovery",
        "video-tile-module",
        "video-tile-rs",
    },
}
PROFILE_KEYS = {"schema", "provider", "transport", "room", "parameters"}


# ai-generated: parsed canonical URI fields.
@dataclass(frozen=True)
class Connection:
    provider: str
    transport: str
    room: str
    key: str
    parameters: dict[str, str]


# ai-generated: reject URI input that came from rendered Markdown or contains controls.
def normalize_uri(value: str) -> str:
    uri = value.strip()
    if len(uri) >= 2 and uri[0] == uri[-1] and uri[0] in {"'", '"'}:
        uri = uri[1:-1].strip()
    if not uri.startswith("olcrtc://"):
        raise ValueError("URI must start with olcrtc://")
    if len(uri) > 16384:
        raise ValueError("URI is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in uri):
        raise ValueError("URI contains control characters")
    if uri.startswith("[") or "](" in uri:
        raise ValueError("copy the raw URI, not a Markdown link")
    return uri


# ai-generated: parse a non-escaped transport parameter payload without silent duplicates.
def parse_parameters(transport: str, payload: str | None) -> dict[str, str]:
    if not payload:
        return {}
    result: dict[str, str] = {}
    for item in payload.split("&"):
        if item.count("=") != 1:
            raise ValueError("transport parameters must use key=value")
        key, value = item.split("=", 1)
        if not key or not value or key in result:
            raise ValueError("transport parameter is empty or duplicated")
        if key not in PARAMETERS[transport]:
            raise ValueError(f"unsupported {transport} parameter: {key}")
        if "%" in key or "%" in value:
            raise ValueError("percent-encoded transport parameters are not supported")
        result[key] = value
    return result


# ai-generated: parse the documented canonical URI v1 format.
def parse_uri(value: str) -> Connection:
    uri = normalize_uri(value)
    body = uri[len("olcrtc://") :]
    try:
        provider, after_provider = body.split("?", 1)
        transport_text, after_transport = after_provider.split("@", 1)
        room, key_and_label = after_transport.rsplit("#", 1)
    except ValueError as exc:
        raise ValueError("URI separators are invalid") from exc
    key = key_and_label.split("$", 1)[0]
    match = URI_PATTERN.fullmatch(transport_text)
    if not match:
        raise ValueError("transport section is invalid")
    transport, payload = match.groups()
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported provider: {provider or '<empty>'}")
    if transport not in TRANSPORTS:
        raise ValueError(f"unsupported transport: {transport or '<empty>'}")
    if not room or any(character in room for character in "@#$<>"):
        raise ValueError("room ID is empty or contains a reserved separator")
    if not HEX_KEY.fullmatch(key):
        raise ValueError("encryption key must contain exactly 64 hex characters")
    validate_room(provider, room)
    validate_compatibility(provider, transport)
    parameters = parse_parameters(transport, payload)
    validate_parameters(transport, parameters)
    return Connection(provider, transport, room, key.lower(), parameters)


# ai-generated: enforce a real Jitsi host and room instead of the invalid any placeholder.
def validate_room(provider: str, room: str) -> None:
    if provider != "jitsi":
        return
    if room.lower() == "any":
        raise ValueError("Jitsi room cannot be 'any'")
    candidate = room if "://" in room else f"https://{room}"
    parsed = urlsplit(candidate)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Jitsi room must be https://host/room or host/room")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Jitsi room must not contain credentials, query or fragment")
    if not parsed.path.strip("/"):
        raise ValueError("Jitsi room URL must contain a room name")


# ai-generated: fail early for combinations documented as unsupported upstream.
def validate_compatibility(provider: str, transport: str) -> None:
    unsupported = {
        ("telemost", "datachannel"),
        ("telemost", "seichannel"),
        ("wbstream", "datachannel"),
    }
    if (provider, transport) in unsupported:
        raise ValueError(f"unsupported provider/transport combination: {provider}/{transport}")


# ai-generated: parse a bounded positive integer parameter.
def integer_parameter(
    parameters: dict[str, str], name: str, minimum: int, maximum: int
) -> int | None:
    if name not in parameters:
        return None
    value = parameters[name]
    if not value.isascii() or not value.isdigit():
        raise ValueError(f"{name} must be an integer")
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


# ai-generated: mirror upstream transport bounds before writing a runtime config.
def validate_parameters(transport: str, parameters: dict[str, str]) -> None:
    if transport == "vp8channel":
        integer_parameter(parameters, "vp8-fps", 1, 240)
        integer_parameter(parameters, "vp8-batch", 1, 1_000_000)
    elif transport == "seichannel":
        integer_parameter(parameters, "fps", 1, 240)
        integer_parameter(parameters, "batch", 1, 1_000_000)
        integer_parameter(parameters, "frag", 1, 60_000)
        integer_parameter(parameters, "ack-ms", 1, 3_600_000)
    elif transport == "videochannel":
        width = integer_parameter(parameters, "video-w", 16, 8192)
        height = integer_parameter(parameters, "video-h", 16, 8192)
        integer_parameter(parameters, "video-fps", 1, 240)
        integer_parameter(parameters, "video-qr-size", 0, 1_000_000)
        integer_parameter(parameters, "video-tile-module", 1, 270)
        integer_parameter(parameters, "video-tile-rs", 0, 200)
        codec = parameters.get("video-codec")
        if codec is not None and codec not in {"qrcode", "tile"}:
            raise ValueError("video-codec must be qrcode or tile")
        recovery = parameters.get("video-qr-recovery")
        if recovery is not None and recovery not in {"low", "medium", "high", "highest"}:
            raise ValueError("video-qr-recovery has an invalid value")
        if codec == "tile" and ((width not in {None, 1080}) or (height not in {None, 1080})):
            raise ValueError("tile codec requires 1080x1080 dimensions")


# ai-generated: render JSON-quoted scalar values, which are valid YAML scalars.
def quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


# ai-generated: build the minimal strict upstream client YAML schema.
def render_config(connection: Connection, key_filename: str) -> str:
    lines = [
        "mode: cnc",
        "auth:",
        f"  provider: {connection.provider}",
        "room:",
        f"  id: {quote(connection.room)}",
        "crypto:",
        f"  key_file: {quote('./' + key_filename)}",
        "net:",
        f"  transport: {connection.transport}",
        '  dns: "8.8.8.8:53"',
        "socks:",
        '  host: "127.0.0.1"',
        "  port: 8808",
        "liveness:",
        "  interval: 10s",
        "  timeout: 15s",
        "  failures: 4",
        "lifecycle:",
        "  max_session_duration: 6h",
    ]
    p = connection.parameters
    if connection.transport == "vp8channel" and p:
        lines.extend(("vp8:", f"  fps: {p.get('vp8-fps', '30')}", f"  batch_size: {p.get('vp8-batch', '64')}"))
    elif connection.transport == "seichannel" and p:
        lines.extend(
            (
                "sei:",
                f"  fps: {p.get('fps', '30')}",
                f"  batch_size: {p.get('batch', '64')}",
                f"  fragment_size: {p.get('frag', '900')}",
                f"  ack_timeout_ms: {p.get('ack-ms', '2000')}",
            )
        )
    elif connection.transport == "videochannel" and p:
        mapping = (
            ("video-w", "width"),
            ("video-h", "height"),
            ("video-fps", "fps"),
            ("video-codec", "codec"),
            ("video-qr-size", "qr_size"),
            ("video-qr-recovery", "qr_recovery"),
            ("video-tile-module", "tile_module"),
            ("video-tile-rs", "tile_rs"),
        )
        lines.append("video:")
        for uri_name, yaml_name in mapping:
            if uri_name not in p:
                continue
            value = p[uri_name]
            rendered = quote(value) if uri_name in {"video-codec", "video-qr-recovery"} else value
            lines.append(f"  {yaml_name}: {rendered}")
    lines.append("debug: false")
    return "\n".join(lines) + "\n"


# ai-generated: atomically switch config to a new versioned key file.
def write_config(config_path: Path, connection: Connection) -> None:
    config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(config_path.parent, 0o700)
    key_filename = f"secret-{secrets.token_hex(6)}.key"
    key_path = config_path.parent / key_filename
    config_temp = config_path.with_name(f".{config_path.name}.{os.getpid()}.tmp")
    committed = False
    try:
        with key_path.open("x", encoding="ascii") as handle:
            os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
            handle.write(connection.key + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        with config_temp.open("x", encoding="utf-8") as handle:
            os.chmod(config_temp, stat.S_IRUSR | stat.S_IWUSR)
            handle.write(render_config(connection, key_filename))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(config_temp, config_path)
        committed = True
    except Exception:
        if not committed:
            key_path.unlink(missing_ok=True)
        config_temp.unlink(missing_ok=True)
        raise
    for old_key in config_path.parent.glob("secret-*.key"):
        if old_key != key_path:
            try:
                old_key.unlink(missing_ok=True)
            except OSError:
                pass


# ai-generated: return the complete non-secret managed profile representation.
def profile_payload(connection: Connection) -> dict[str, object]:
    return {
        "schema": 1,
        "provider": connection.provider,
        "transport": connection.transport,
        "room": connection.room,
        "parameters": dict(connection.parameters),
    }


# ai-generated: atomically write a root-owned non-secret profile for the web UI.
def write_profile(profile_path: Path, connection: Connection) -> None:
    profile_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile_temp = profile_path.with_name(f".{profile_path.name}.{os.getpid()}.tmp")
    try:
        with profile_temp.open("x", encoding="utf-8") as handle:
            os.chmod(profile_temp, stat.S_IRUSR | stat.S_IWUSR)
            json.dump(profile_payload(connection), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(profile_temp, profile_path)
    except Exception:
        profile_temp.unlink(missing_ok=True)
        raise


# ai-generated: validate a settings object supplied by the authenticated web UI.
def connection_from_settings(payload: object, key: str) -> Connection:
    if not isinstance(payload, dict) or set(payload) != PROFILE_KEYS - {"schema"}:
        raise ValueError("settings must contain provider, transport, room and parameters")
    provider = payload.get("provider")
    transport = payload.get("transport")
    room = payload.get("room")
    parameters = payload.get("parameters")
    if not all(isinstance(item, str) for item in (provider, transport, room)):
        raise ValueError("provider, transport and room must be strings")
    if provider not in PROVIDERS or transport not in TRANSPORTS:
        raise ValueError("provider or transport is unsupported")
    if not isinstance(parameters, dict) or not all(
        isinstance(name, str) and isinstance(value, str) for name, value in parameters.items()
    ):
        raise ValueError("parameters must be an object of strings")
    if len(room) > 4096 or any(ord(character) < 32 for character in room):
        raise ValueError("room contains invalid characters")
    validate_room(provider, room)
    validate_compatibility(provider, transport)
    unknown = set(parameters) - PARAMETERS[transport]
    if unknown:
        raise ValueError(f"unsupported {transport} parameter: {sorted(unknown)[0]}")
    validate_parameters(transport, parameters)
    if not HEX_KEY.fullmatch(key):
        raise ValueError("stored encryption key is invalid")
    return Connection(provider, transport, room, key.lower(), dict(parameters))


# ai-generated: read the single managed key without returning it to the web process.
def read_current_key(config_path: Path) -> str:
    key_files = list(config_path.parent.glob("secret-*.key"))
    if len(key_files) != 1:
        raise ValueError("managed configuration must contain exactly one secret key file")
    key = key_files[0].read_text(encoding="ascii").strip()
    if not HEX_KEY.fullmatch(key):
        raise ValueError("stored encryption key is invalid")
    return key


# ai-generated: load and revalidate a persisted profile before displaying it.
def load_profile(profile_path: Path) -> dict[str, object]:
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != PROFILE_KEYS or payload.get("schema") != 1:
        raise ValueError("managed profile schema is invalid")
    settings = {name: payload[name] for name in PROFILE_KEYS - {"schema"}}
    connection = connection_from_settings(settings, "0" * 64)
    return profile_payload(connection)


# ai-generated: write runtime config and the matching non-secret management profile.
def write_managed_config(config_path: Path, profile_path: Path, connection: Connection) -> None:
    write_config(config_path, connection)
    write_profile(profile_path, connection)


# ai-generated: command-line entrypoint for installation and later reconfiguration.
def main() -> int:
    parser = argparse.ArgumentParser()
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--uri-file", type=Path)
    inputs.add_argument("--settings-file", type=Path)
    inputs.add_argument("--show", action="store_true")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.show:
            print(json.dumps(load_profile(args.profile), ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.uri_file is not None:
            uri = args.uri_file.read_text(encoding="utf-8")
            connection = parse_uri(uri)
        else:
            payload = json.loads(args.settings_file.read_text(encoding="utf-8"))
            connection = connection_from_settings(payload, read_current_key(args.config))
        write_managed_config(args.config, args.profile, connection)
        print(f"configured {connection.provider}/{connection.transport}")
        return 0
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"URI import error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
