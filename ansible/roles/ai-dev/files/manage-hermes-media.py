#!/usr/bin/env python3
"""Conservatively reconcile Hermes' optional media-broker MCP entry."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import stat
import tempfile
from urllib.parse import urlsplit

import yaml

MARKER_PREFIX = "ansible-managed-hermes-media-broker-v1"
TOKEN_KEY = "MEDIA_BROKER_TOKEN"
TOKEN_REFERENCE = "${MEDIA_BROKER_TOKEN}"
TOKEN_LINE = re.compile(r"^\s*(?:export\s+)?MEDIA_BROKER_TOKEN\s*=")
TOKEN_VALUE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
TOOLS = [
    "arr_library_inventory",
    "arr_quality_profiles",
    "arr_root_folders",
    "arr_search_candidates",
    "arr_season_inventory",
    "arr_album_inventory",
    "tautulli_play_history",
    "jellyfin_play_history",
    "jellyfin_users",
    "torrent_client_stats",
    "torrent_client_inventory",
    "torrent_client_check_paths",
    "arr_request_media",
    "arr_search_item",
    "arr_unmonitor_media",
    "arr_monitor_media",
    "arr_set_season_monitoring",
    "arr_set_album_monitored",
    "arr_delete_media",
]


def fail(message: str) -> None:
    raise SystemExit(message)


def read_yaml(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except (OSError, yaml.YAMLError):
        fail("invalid Hermes YAML")
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail("invalid Hermes YAML")
    return value


def marker_state(marker: pathlib.Path) -> dict | None:
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 256:
                return None
            lines = os.read(fd, 257).decode("utf-8").splitlines()
        finally:
            os.close(fd)
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0] != MARKER_PREFIX:
        return None
    state = {"env_final_newline": True}
    for line in lines[1:]:
        key, separator, value = line.partition("=")
        if separator and key == "env_final_newline" and value in ("0", "1"):
            state[key] = value == "1"
    return state


def managed_entry(url: str) -> dict:
    return {
        "url": url,
        "headers": {"Authorization": f"Bearer {TOKEN_REFERENCE}"},
        "tools": {"include": TOOLS, "resources": False, "prompts": False},
        "sampling": {"enabled": False},
        "elicitation": {"enabled": False},
        "enabled": True,
    }


def prepare_yaml(path: pathlib.Path, enabled: bool, url: str, takeover: bool, owned: bool) -> tuple[str, bool]:
    if not path.exists() and not enabled:
        return "", False
    before = read_yaml(path)
    servers = before.get("mcp_servers")
    if servers is not None and not isinstance(servers, dict):
        fail("invalid Hermes mcp_servers configuration")
    servers = dict(servers or {})
    existing = servers.get("media_broker")
    if existing is not None and not isinstance(existing, dict):
        fail("invalid Hermes media broker configuration")

    if enabled:
        if existing is not None and not owned and not takeover:
            fail("unowned Hermes media broker configuration")
        servers["media_broker"] = managed_entry(url)
        before["mcp_servers"] = servers
    elif owned and existing is not None:
        del servers["media_broker"]
        before["mcp_servers"] = servers
    rendered = yaml.safe_dump(before, sort_keys=False)
    original = yaml.safe_dump(read_yaml(path), sort_keys=False) if path.exists() else ""
    return rendered, rendered != original


def prepare_env(path: pathlib.Path, enabled: bool, token: str, owned: bool, original_final_newline: bool) -> tuple[str, bool]:
    if not path.exists():
        lines: list[str] = []
    else:
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            fail("unable to read Hermes environment")
    matches = [line for line in lines if TOKEN_LINE.match(line)]
    if matches and not owned:
        fail("unowned Hermes media token")
    kept = [line for line in lines if not TOKEN_LINE.match(line)]
    content = "".join(kept)
    if enabled:
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"{TOKEN_KEY}={token}\n"
    elif owned and not original_final_newline and content.endswith("\n"):
        content = content[:-1]
    original = "".join(lines)
    return content, content != original


def atomic_write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def validate_url(value: str, host: str, port: int) -> None:
    try:
        parsed = urlsplit(value)
        parsed_port = parsed.port
    except ValueError:
        fail("invalid media broker endpoint")
    if (
        parsed.scheme != "http"
        or parsed.hostname != host
        or parsed_port != port
        or parsed.path != "/mcp"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        fail("invalid media broker endpoint")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", required=True, type=pathlib.Path)
    parser.add_argument("--env", required=True, type=pathlib.Path)
    parser.add_argument("--marker", required=True, type=pathlib.Path)
    parser.add_argument("--url", required=True)
    parser.add_argument("--allowed-host", required=True)
    parser.add_argument("--allowed-port", required=True, type=int)
    parser.add_argument("--mode", choices=("enabled", "disabled"), required=True)
    parser.add_argument("--takeover", choices=("true", "false"), default="false")
    args = parser.parse_args()
    enabled = args.mode == "enabled"
    takeover = args.takeover == "true"
    if enabled:
        validate_url(args.url, args.allowed_host, args.allowed_port)
    state = marker_state(args.marker)
    owned = state is not None
    if not enabled and not owned:
        if args.config.exists():
            read_yaml(args.config)
        print(json.dumps({"changed": False}, separators=(",", ":")))
        return

    token = os.environ.get(TOKEN_KEY, "")
    if enabled and not TOKEN_VALUE.fullmatch(token):
        fail("media broker token must be 32-256 URL-safe characters")
    original_env = args.env.read_text(encoding="utf-8") if args.env.exists() else ""
    original_final_newline = original_env.endswith("\n")
    if state is not None:
        original_final_newline = state.get("env_final_newline", True)
    yaml_content, yaml_changed = prepare_yaml(args.config, enabled, args.url, takeover, owned)
    env_content, env_changed = prepare_env(args.env, enabled, token, owned, original_final_newline)

    # Establish recoverable ownership only after all input/collision validation,
    # but before replacing either file. A crash after this point is retryable.
    mode_changed = enabled and any(
        path.exists() and stat.S_IMODE(path.stat().st_mode) != 0o600
        for path in (args.config, args.env, args.marker)
    )
    changed = yaml_changed or env_changed or (enabled != owned) or mode_changed
    if enabled and not owned:
        marker_content = f"{MARKER_PREFIX}\nenv_final_newline={'1' if original_final_newline else '0'}\n"
        atomic_write(args.marker, marker_content)
        changed = True
    if os.environ.get("HERMES_MEDIA_TEST_FAIL_AFTER_MARKER") == "1":
        fail("injected test failure")
    if yaml_changed:
        atomic_write(args.config, yaml_content)
    if os.environ.get("HERMES_MEDIA_TEST_FAIL_AFTER_YAML") == "1":
        fail("injected test failure")
    if env_changed:
        atomic_write(args.env, env_content)
    if enabled:
        for path in (args.config, args.env, args.marker):
            if path.exists():
                os.chmod(path, 0o600)
    elif owned:
        try:
            args.marker.unlink()
        except FileNotFoundError:
            pass
    print(json.dumps({"changed": changed}, separators=(",", ":")))


if __name__ == "__main__":
    main()
