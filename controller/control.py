#!/usr/bin/env python3
"""Restricted local controller for OpenSim AI Bridge.

The web server can only send one of six fixed JSON commands over a Unix socket.
The process does not accept shell commands, paths or unit names from clients.
"""
import argparse
import json
import os
import stat
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import sys
import tempfile
import time

UNIT = "opensim-ai-bridge.service"
COMMANDS = frozenset(("status", "start", "stop", "restart", "firestorm", "resume", "get_settings", "save_settings"))
MAX_REQUEST = 4096


class ControlError(Exception):
    pass


def systemctl(*arguments):
    try:
        result = subprocess.run(
            ("/usr/bin/systemctl", *arguments, UNIT),
            text=True, capture_output=True, timeout=30, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControlError(f"systemctl unavailable: {type(exc).__name__}") from exc
    if result.returncode:
        # Do not forward arbitrary service output to the public-facing frontend.
        raise ControlError(f"systemctl operation failed (exit {result.returncode})")
    return result.stdout


def service_state():
    values = {}
    output = systemctl("show", "--property=ActiveState,SubState,UnitFileState")
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return {
        "active": values.get("ActiveState", "unknown"),
        "substate": values.get("SubState", "unknown"),
        "enabled": values.get("UnitFileState", "unknown"),
    }


def create_lock(path):
    # Atomic file replacement prevents a partial lock.
    fd, temp = tempfile.mkstemp(prefix=".maintenance-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("Firestorm mode: reconnection disabled until administrator resumes.\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def avatar_presence(install):
    """Report only fresh, validated heartbeat values, never arbitrary bot data."""
    file = install / "data" / "avatar-status.json"
    try:
        if not file.is_file() or file.stat().st_size > 4096:
            return {"connected": False, "state": "unavailable"}
        data = json.loads(file.read_text(encoding="utf-8"))
        ts = data.get("updatedUtc")
        fresh = isinstance(ts, int) and 0 <= time.time() - ts < 15
        online = fresh and data.get("connected") is True and data.get("state") == "online"
        region = data.get("region")
        coords = (data.get("x"), data.get("y"), data.get("z"))
        if not online or not isinstance(region, str) or len(region) > 128 or not all(type(v) in (float, int) and abs(v) < 1e7 for v in coords):
            return {"connected": False, "state": "stale" if not fresh else "offline"}
        return {
            "connected": True,
            "state": "online",
            "region": region,
            "position": {"x": round(coords[0], 2), "y": round(coords[1], 2), "z": round(coords[2], 2)},
            "ageSeconds": max(0, int(time.time() - ts))
        }
    except (OSError, ValueError, TypeError, AttributeError):
        return {"connected": False, "state": "unavailable"}



def config_file(install):
    path = install / "appsettings.json"
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 131072 or (metadata.st_mode & 0o022):
        raise ControlError("Configuration file has unsafe permissions or size")
    return path, metadata


def read_settings(install):
    try:
        path, _ = config_file(install)
        data = json.loads(path.read_text(encoding="utf-8"))
        grid = data.get("Grid", {})
        location = grid.get("StartLocation", {})
        pos = location.get("Position", {})
        bot = data.get("Bot", {})
        return {
            "region": str(location.get("RegionName", "")),
            "x": pos.get("X", 128), "y": pos.get("Y", 128), "z": pos.get("Z", 25),
            "enableIM": bot.get("EnableIM", True),
            "enableLocalChat": bot.get("EnableLocalChat", True),
            "reconnectEnabled": bot.get("ReconnectEnabled", True),
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ControlError("Unable to read bot settings") from exc


def save_settings(install, values):
    if not isinstance(values, dict) or set(values) != {"region", "x", "y", "z", "enableIM", "enableLocalChat", "reconnectEnabled"}:
        raise ControlError("Invalid settings fields")
    region = values.get("region")
    if not isinstance(region, str) or not 1 <= len(region.strip()) <= 80 or any(ord(c) < 32 for c in region):
        raise ControlError("Invalid region name")
    for key, low, high in (("x", 0, 256), ("y", 0, 256), ("z", 0, 4096)):
        if type(values[key]) is not int or not low <= values[key] <= high:
            raise ControlError(f"Invalid {key} position")
    for key in ("enableIM", "enableLocalChat", "reconnectEnabled"):
        if type(values[key]) is not bool:
            raise ControlError(f"Invalid {key} flag")
    try:
        path, metadata = config_file(install)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("Grid"), dict):
            raise ControlError("Invalid original configuration")
        grid = data["Grid"]
        location = grid.setdefault("StartLocation", {})
        location["RegionName"] = region.strip()
        location["Position"] = {"X": values["x"], "Y": values["y"], "Z": values["z"]}
        bot = data.setdefault("Bot", {})
        bot["EnableIM"] = values["enableIM"]
        bot["EnableLocalChat"] = values["enableLocalChat"]
        bot["ReconnectEnabled"] = values["reconnectEnabled"]
        fd, temp = tempfile.mkstemp(prefix=".appsettings-", dir=str(install))
        try:
            os.fchmod(fd, stat.S_IMODE(metadata.st_mode))
            os.fchown(fd, metadata.st_uid, metadata.st_gid)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ControlError("Failed to save bot settings") from exc
    return {"saved": True, "restartRequired": True}


def execute(command, lock, confirm, install, settings=None):
    if command not in COMMANDS:
        raise ControlError("Unsupported command")

    if command == "get_settings":
        return read_settings(install)
    if command == "save_settings":
        return save_settings(install, settings)
    if command == "status":
        return {**service_state(), "maintenance": lock.exists(), "avatar": avatar_presence(install)}

    if command in ("start", "restart") and lock.exists():
        raise ControlError("Firestorm maintenance is enabled; resume first")

    if command == "firestorm":
        # Persist the lock BEFORE stopping so a simultaneous restart cannot log in.
        create_lock(lock)
        systemctl("stop")
    elif command == "resume":
        if confirm is not True:
            raise ControlError("Firestorm disconnection confirmation required")
        # Only remove the lock after confirmation.
        lock.unlink(missing_ok=True)
        systemctl("start")
    elif command == "start":
        systemctl("start")
    elif command == "stop":
        systemctl("stop")
    elif command == "restart":
        systemctl("restart")
    return {**service_state(), "maintenance": lock.exists()}


def handle(client, allowed_uid, lock, install):
    # Authenticate the OS-level peer: only the Apache/PHP account.
    creds = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    _, uid, _ = struct.unpack("3i", creds)
    if uid != allowed_uid:
        return {"ok": False, "error": "Unauthorized local peer"}
    client.settimeout(5.0)
    buf = b""
    while b"\n" not in buf and len(buf) <= MAX_REQUEST:
        chunk = client.recv(1024)
        if not chunk:
            break
        buf += chunk
    if len(buf) > MAX_REQUEST or b"\n" not in buf:
        return {"ok": False, "error": "Malformed request"}
    try:
        msg = json.loads(buf.split(b"\n", 1)[0])
        if not isinstance(msg, dict) or set(msg) - {"action", "confirm", "settings"}:
            raise ControlError("Invalid request")
        result = execute(msg.get("action"), lock, msg.get("confirm") is True, install, msg.get("settings"))
        return {"ok": True, "result": result}
    except (ValueError, TypeError, ControlError) as exc:
        return {"ok": False, "error": str(exc)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--socket", default="/run/opensim-ai-bridge-control/control.sock")
    args = parser.parse_args()
    install = Path(args.install_dir).resolve(strict=True)
    lock = install / "maintenance.lock"
    socket_path = Path(args.socket)
    allowed_uid = pwd.getpwnam("www-data").pw_uid

    # Parent directory must have been created by systemd RuntimeDirectory.
    if not socket_path.parent.is_dir():
        raise SystemExit("Missing RuntimeDirectory for the control socket")
    socket_path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chown(socket_path, 0, pwd.getpwnam("www-data").pw_gid)
    os.chmod(socket_path, 0o660)
    server.listen(8)
    print("OpenSim AI Bridge local controller ready", flush=True)
    try:
        while True:
            client, _ = server.accept()
            with client:
                try:
                    response = handle(client, allowed_uid, lock, install)
                except (OSError, UnicodeDecodeError) as exc:
                    response = {"ok": False, "error": type(exc).__name__}
                try:
                    client.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode())
                except OSError:
                    pass
    finally:
        server.close()
        socket_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
