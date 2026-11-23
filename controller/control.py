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
import re
import uuid
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import multi_bot
import provider_profiles

UNIT = "opensim-ai-bridge.service"
COMMANDS = frozenset(("status", "start", "stop", "restart", "firestorm", "resume", "get_settings", "save_settings", "get_ai_settings", "save_ai_settings", "list_bots", "create_bot", "delete_bot", "fleet_status", "fleet_stop", "fleet_resume", "knowledge_status", "knowledge_refresh", "get_multi_ai_settings", "save_multi_ai_settings"))
MAX_REQUEST = 12288
FLEET_ROOT = Path("/var/lib/opensim-ai-bridge")
FLEET_LOCK = FLEET_ROOT / "global-maintenance.lock"
FLEET_SNAPSHOT = FLEET_ROOT / "global-maintenance-state.json"
# Per-service CPU samples live only in the controller process, never in a Web session.
_CPU_SAMPLES = {}


class ControlError(Exception):
    pass


def systemctl(*arguments, unit=UNIT):
    try:
        result = subprocess.run(
            ("/usr/bin/systemctl", *arguments, unit),
            text=True, capture_output=True, timeout=30, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControlError(f"systemctl unavailable: {type(exc).__name__}") from exc
    if result.returncode:
        # Do not forward arbitrary service output to the public-facing frontend.
        raise ControlError(f"systemctl operation failed (exit {result.returncode})")
    return result.stdout


def _systemd_metric_number(raw):
    """systemd may return '[not set]' or UINT64_MAX for unavailable accounting."""
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
        return None
    value = int(raw)
    if value >= 2**64 - 1:
        return None
    return value


def resource_usage(unit, active, properties, now=None):
    """CPU % of one logical core, measured between controller reads (can exceed 100%)."""
    if active != "active":
        _CPU_SAMPLES.pop(unit, None)
        return {"memoryMb": None, "cpuPercent": None}
    memory = _systemd_metric_number(properties.get("MemoryCurrent"))
    cpu_ns = _systemd_metric_number(properties.get("CPUUsageNSec"))
    observed_at = time.monotonic() if now is None else now
    previous = _CPU_SAMPLES.get(unit)
    percent = None
    if cpu_ns is not None:
        _CPU_SAMPLES[unit] = (observed_at, cpu_ns)
        if previous is not None:
            elapsed = observed_at - previous[0]
            cpu_delta = cpu_ns - previous[1]
            if elapsed >= 1 and cpu_delta >= 0:
                percent = round(100.0 * cpu_delta / (elapsed * 1_000_000_000), 1)
    else:
        _CPU_SAMPLES.pop(unit, None)
    return {"memoryMb": round(memory / (1024 * 1024), 1) if memory is not None else None,
            "cpuPercent": percent}


def service_state(unit=UNIT, with_metrics=False):
    values = {}
    properties = "ActiveState,SubState,UnitFileState"
    if with_metrics:
        properties += ",MemoryCurrent,CPUUsageNSec"
    output = systemctl("show", f"--property={properties}", unit=unit)
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    result = {
        "active": values.get("ActiveState", "unknown"),
        "substate": values.get("SubState", "unknown"),
        "enabled": values.get("UnitFileState", "unknown"),
    }
    if with_metrics:
        result["resources"] = resource_usage(unit, result["active"], values)
    return result


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


def read_ai_settings(install):
    try:
        path, _ = config_file(install)
        doc = json.loads(path.read_text(encoding="utf-8"))
        ai = doc.get("Ai") or {}
        key_file = install / "ai-api-key.txt"
        return {
            "enabled": ai.get("Enabled", False),
            "provider": ai.get("Provider", "OpenAI"),
            "model": ai.get("Model", "gpt-4.1-mini"),
            "authorizedUuids": ai.get("AuthorizedUuidList", []),
            "publicAccess": ai.get("PublicAccess", False),
            "maxRequestsPerHour": ai.get("MaxRequestsPerHour", 30),
            "minSecondsBetweenRequests": ai.get("MinSecondsBetweenRequests", 15),
            "systemPrompt": ai.get("SystemPrompt", "Tu es un assistant BloodMoon. Réponds dans la langue de la personne, sans inventer."),
            "hasKey": key_file.is_file() and key_file.stat().st_size > 0,
        }
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ControlError("Could not read remote AI settings") from exc


def read_multi_ai_settings(install):
    try:
        path, _ = config_file(install)
        ai = (json.loads(path.read_text(encoding="utf-8")).get("Ai") or {})
        return {
            "enabled": bool(ai.get("Enabled", False)),
            "mode": ai.get("Mode", "single"),
            "profiles": provider_profiles.existing_profiles(ai, install),
            "maxRequestsPerHour": ai.get("MaxRequestsPerHour", 30),
            "minSecondsBetweenRequests": ai.get("MinSecondsBetweenRequests", 15),
            "systemPrompt": ai.get("SystemPrompt", "Tu es un assistant BloodMoon. Réponds dans la langue de la personne."),
        }
    except (OSError, ValueError, TypeError, KeyError, provider_profiles.ProfileError) as exc:
        raise ControlError("Cannot read provider profiles") from exc


def save_multi_ai_settings(install, values):
    try:
        ai = provider_profiles.normalize(values)
    except provider_profiles.ProfileError as exc:
        raise ControlError(str(exc)) from exc
    # Each enabled provider requires its own credential. Legacy provider's secret
    # remains valid until an explicit, safe migration is performed.
    supplied = values["profiles"]
    for profile in ai["Profiles"]:
        if not profile["Enabled"] or not profile["Verified"]:
            continue
        provider = profile["Provider"]
        secret_file = provider_profiles.provider_key_path(install, provider)
        legacy_file = install / "ai-api-key.txt"
        entered = any(p["provider"] == provider and p["apiKey"] for p in supplied)
        existing = secret_file.is_file() and secret_file.stat().st_size > 0
        old = provider == read_ai_settings(install)["provider"] and legacy_file.is_file()
        if not (entered or existing or old):
            raise ControlError("The active provider needs a private API key")
    try:
        path, metadata = config_file(install)
        doc = json.loads(path.read_text(encoding="utf-8"))
        original = doc.get("Ai") or {}
        # Keep legacy fields (and legacy secret) for safe rollback.
        doc["Ai"] = {**original, **ai}
        provider_profiles.save_keys(install, supplied, metadata.st_uid, metadata.st_gid)
        fd, temporary = tempfile.mkstemp(prefix=".multi-ai-", dir=str(install))
        try:
            os.fchmod(fd, stat.S_IMODE(metadata.st_mode))
            os.fchown(fd, metadata.st_uid, metadata.st_gid)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(doc, output, indent=2, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except (OSError, ValueError, TypeError, KeyError, provider_profiles.ProfileError) as exc:
        raise ControlError("Could not save multi-provider configuration") from exc
    return {"saved": True, "restartRequired": True}


def save_ai_settings(install, values):
    if not isinstance(values, dict) or set(values) != {"enabled", "provider", "model", "authorizedUuids", "publicAccess", "maxRequestsPerHour", "minSecondsBetweenRequests", "systemPrompt", "apiKey"}:
        raise ControlError("Invalid remote AI settings fields")
    if type(values["enabled"]) is not bool or values["provider"] not in ("OpenAI", "Groq", "OpenRouter"):
        raise ControlError("Unsupported AI provider or enabled flag")
    if type(values["publicAccess"]) is not bool or (values["publicAccess"] and values["provider"] != "Groq"):
        raise ControlError("Public AI access is supported only with Groq")
    model = values["model"]
    if not isinstance(model, str) or re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", model) is None:
        raise ControlError("Invalid AI model identifier")
    prompt = values["systemPrompt"]
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 600 or any(ord(c) < 32 and c not in "\n\t" for c in prompt):
        raise ControlError("Invalid system prompt")
    uuids = values["authorizedUuids"]
    if not isinstance(uuids, list) or len(uuids) > 12 or any(not isinstance(u, str) or len(u) > 36 for u in uuids):
        raise ControlError("Invalid UUID allowlist")
    try:
        allowed = list(dict.fromkeys(str(uuid.UUID(u)) for u in uuids))
    except (ValueError, AttributeError) as exc:
        raise ControlError("One or more authorized UUIDs are invalid") from exc
    hourly = values["maxRequestsPerHour"]
    cooldown = values["minSecondsBetweenRequests"]
    if type(hourly) is not int or not 1 <= hourly <= 120 or type(cooldown) is not int or not 5 <= cooldown <= 3600:
        raise ControlError("Invalid AI request limits")
    key = values["apiKey"]
    if not isinstance(key, str) or len(key) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ControlError("Invalid secret key")
    secret_path = install / "ai-api-key.txt"
    if secret_path.is_symlink():
        raise ControlError("Unsafe AI secret path")
    if values["enabled"] and ((not allowed and not values["publicAccess"]) or (not key and not secret_path.is_file())):
        raise ControlError("Enable AI only after adding an API key and at least one authorized UUID")
    try:
        path, meta = config_file(install)
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["Ai"] = {
            "Enabled": values["enabled"], "Provider": values["provider"], "Model": model,
            "ApiKeyEnv": "OSAI_AI_API_KEY",
            "AuthorizedUuidList": allowed, "PublicAccess": values["publicAccess"], "MaxRequestsPerHour": hourly,
            "MinSecondsBetweenRequests": cooldown, "SystemPrompt": prompt.strip(),
        }
        if key:
            fd, tmp = tempfile.mkstemp(prefix=".ai-key-", dir=str(install))
            try:
                os.fchmod(fd, 0o600)
                os.fchown(fd, meta.st_uid, meta.st_gid)
                with os.fdopen(fd, "w", encoding="utf-8") as output:
                    output.write(key + "\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(tmp, secret_path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        fd, tmp = tempfile.mkstemp(prefix=".ai-settings-", dir=str(install))
        try:
            os.fchmod(fd, stat.S_IMODE(meta.st_mode))
            os.fchown(fd, meta.st_uid, meta.st_gid)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(doc, output, indent=2, ensure_ascii=False)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise ControlError("Could not save remote AI settings") from exc
    return {"saved": True, "restartRequired": True}


def fleet_units():
    return [UNIT] + [multi_bot.bot_unit(bot_id) for bot_id in multi_bot.instances()]


def fleet_status():
    units = fleet_units()
    running = sum(service_state(unit)["active"] == "active" for unit in units)
    return {"maintenance": FLEET_LOCK.exists(), "total": len(units), "running": running}


def fleet_stop(confirmed):
    if not confirmed:
        raise ControlError("Confirm global maintenance")
    if FLEET_LOCK.exists():
        return fleet_status()
    units = fleet_units()
    prior = [unit for unit in units if service_state(unit)["active"] == "active"]
    fd, tmp = tempfile.mkstemp(prefix=".fleet-", dir=str(FLEET_ROOT))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump({"running": prior}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, FLEET_SNAPSHOT)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    create_lock(FLEET_LOCK)
    # Send a single stop transaction to systemd. Stopping bots sequentially could
    # exceed the web controller's 35-second socket timeout with many instances.
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "stop", *units],
            text=True, capture_output=True, timeout=30, check=False,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControlError("Global maintenance active; stop operation timed out") from exc
    if result.returncode:
        raise ControlError("Global maintenance active; one or more bot services did not stop")
    return fleet_status()


def fleet_resume(confirmed, legacy_install):
    if not confirmed:
        raise ControlError("Confirm global resume")
    if not FLEET_LOCK.exists():
        return fleet_status()
    if not FLEET_SNAPSHOT.is_file():
        raise ControlError("Missing maintenance snapshot")
    prior = json.loads(FLEET_SNAPSHOT.read_text(encoding="utf-8"))["running"]
    allowed = set(fleet_units())
    if not isinstance(prior, list) or any(type(u) is not str or u not in allowed for u in prior):
        raise ControlError("Invalid maintenance snapshot")
    FLEET_LOCK.unlink()
    failed = 0
    for unit in prior:
        if unit == UNIT:
            personal_lock = legacy_install / "maintenance.lock"
        else:
            bot_id = unit[len("opensim-ai-bridge@"):-len(".service")]
            personal_lock = multi_bot.bot_path(bot_id) / "maintenance.lock"
        if personal_lock is not None and personal_lock.exists():
            continue
        try:
            systemctl("start", unit=unit)
        except ControlError:
            failed += 1
    if failed:
        raise ControlError(f"Global maintenance ended, but {failed} service(s) failed to start")
    FLEET_SNAPSHOT.unlink(missing_ok=True)
    return fleet_status()


def knowledge_status(install):
    unit = "opensim-ai-bridge-knowledge.service"
    state = service_state(unit)
    db = install / "data" / "bloodmoon_knowledge.db"
    counts = []
    if db.is_file():
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2) as conn:
                counts = [
                    {"source": source, "pages": pages, "passages": passages}
                    for source, pages, passages in conn.execute("""
                        SELECT source, count(*),
                        (SELECT count(*) FROM knowledge_passages p WHERE p.source=d.source)
                        FROM knowledge_pages d GROUP BY source ORDER BY source
                    """).fetchall()
                ]
        except (sqlite3.Error, OSError):
            counts = []
    # A completed oneshot is 'inactive'; distinguish a successful exit from failure.
    # Query only fixed systemd properties; never return untrusted journal contents.
    try:
        raw = systemctl("show", "--property=Result,ExecMainStatus,ExecMainExitTimestamp",
                        unit=unit)
        details = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    except ControlError:
        details = {}
    return {"service": state.get("active", "unknown"),
            "result": details.get("Result", "unknown"),
            "exitCode": details.get("ExecMainStatus", ""),
            "finishedAt": details.get("ExecMainExitTimestamp", ""),
            "sources": counts, "database": db.is_file()}


def knowledge_refresh(install):
    unit = "opensim-ai-bridge-knowledge.service"
    if service_state(unit)["active"] in ("active", "activating", "reloading"):
        # A oneshot service remains "activating" while its long job runs.
        return {"alreadyRunning": True}
    # Start asynchronous, independent systemd service, never in the Web worker.
    result = subprocess.run(
        ["/usr/bin/systemctl", "start", "--no-block", unit],
        capture_output=True, text=True, timeout=10, check=False,
        env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    if result.returncode:
        raise ControlError("Knowledge refresh service could not be started")
    return {"started": True}


def execute(command, lock, confirm, install, settings=None, bot_id="main", credentials=None, expected_name=None):
    if command not in COMMANDS:
        raise ControlError("Unsupported command")

    if command == "get_multi_ai_settings":
        return read_multi_ai_settings(install)
    if command == "save_multi_ai_settings":
        return save_multi_ai_settings(install, settings)
    if command == "knowledge_status":
        return knowledge_status(install)
    if command == "knowledge_refresh":
        return knowledge_refresh(install)
    if command == "fleet_status":
        return fleet_status()
    if command == "fleet_stop":
        return fleet_stop(confirm)
    if command == "fleet_resume":
        return fleet_resume(confirm, install)
    if FLEET_LOCK.exists() and command in ("create_bot", "delete_bot", "start", "restart", "resume"):
        raise ControlError("Global maintenance active")
    if command == "delete_bot":
        if not confirm:
            raise ControlError("Confirm avatar removal")
        try:
            return multi_bot.delete_bot(bot_id, expected_name)
        except multi_bot.BotRegistryError as exc:
            raise ControlError(str(exc)) from exc
    if command == "create_bot":
        try:
            return multi_bot.create_bot(credentials, install)
        except multi_bot.BotRegistryError as exc:
            raise ControlError(str(exc)) from exc
    if command == "list_bots":
        bots = [{"id": "main", "firstName": "", "lastName": "", "region": ""}]
        try:
            legacy = json.loads((install / "appsettings.json").read_text(encoding="utf-8"))["Grid"]
            bots[0].update(firstName=legacy.get("AvatarFirstName", ""), lastName=legacy.get("AvatarLastName", ""),
                           region=legacy.get("StartLocation", {}).get("RegionName", ""))
            for instance_id in multi_bot.instances():
                bots.append(multi_bot.get_metadata(instance_id))
        except (OSError, KeyError, ValueError, TypeError, multi_bot.BotRegistryError) as exc:
            raise ControlError("Unable to list bots") from exc
        return {"bots": bots}
    if bot_id != "main":
        try:
            install = multi_bot.bot_path(bot_id)
            if not (install / "appsettings.json").is_file():
                raise ControlError("Unknown bot")
            lock = install / "maintenance.lock"
            unit = multi_bot.bot_unit(bot_id)
        except multi_bot.BotRegistryError as exc:
            raise ControlError(str(exc)) from exc
    else:
        unit = UNIT
    if command == "get_ai_settings":
        return read_ai_settings(install)
    if command == "save_ai_settings":
        return save_ai_settings(install, settings)
    if command == "get_settings":
        return read_settings(install)
    if command == "save_settings":
        return save_settings(install, settings)
    if command == "status":
        return {**service_state(unit, with_metrics=True), "maintenance": lock.exists(), "avatar": avatar_presence(install)}

    if command in ("start", "restart") and lock.exists():
        raise ControlError("Firestorm maintenance is enabled; resume first")

    if command == "firestorm":
        # Persist the lock BEFORE stopping so a simultaneous restart cannot log in.
        create_lock(lock)
        systemctl("stop", unit=unit)
    elif command == "resume":
        if confirm is not True:
            raise ControlError("Firestorm disconnection confirmation required")
        # Only remove the lock after confirmation.
        lock.unlink(missing_ok=True)
        systemctl("start", unit=unit)
    elif command == "start":
        systemctl("start", unit=unit)
    elif command == "stop":
        systemctl("stop", unit=unit)
    elif command == "restart":
        systemctl("restart", unit=unit)
    return {**service_state(unit), "maintenance": lock.exists()}


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
        if not isinstance(msg, dict) or set(msg) - {"action", "confirm", "settings", "botId", "credentials", "expectedName"}:
            raise ControlError("Invalid request")
        result = execute(msg.get("action"), lock, msg.get("confirm") is True, install, msg.get("settings"), msg.get("botId", "main"), msg.get("credentials"), msg.get("expectedName"))
        return {"ok": True, "result": result}
    except (ValueError, TypeError, ControlError, multi_bot.BotRegistryError) as exc:
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
