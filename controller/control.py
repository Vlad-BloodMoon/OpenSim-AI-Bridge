#!/usr/bin/env python3
"""Restricted local controller for OpenSim AI Bridge.

The web server can only send one of six fixed JSON commands over a Unix socket.
The process does not accept shell commands, paths or unit names from clients.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import sys
import tempfile

UNIT = "opensim-ai-bridge.service"
COMMANDS = frozenset(("status", "start", "stop", "restart", "firestorm", "resume"))
MAX_REQUEST = 2048


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


def execute(command, lock, confirm):
    if command not in COMMANDS:
        raise ControlError("Unsupported command")

    if command == "status":
        return {**service_state(), "maintenance": lock.exists()}

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


def handle(client, allowed_uid, lock):
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
        if not isinstance(msg, dict) or set(msg) - {"action", "confirm"}:
            raise ControlError("Invalid request")
        result = execute(msg.get("action"), lock, msg.get("confirm") is True)
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
                    response = handle(client, allowed_uid, lock)
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
