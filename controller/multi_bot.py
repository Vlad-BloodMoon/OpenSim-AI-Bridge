"""Safe multi-avatar registry for the OpenSim AI Bridge local controller.

Only server-generated hexadecimal bot IDs are used in systemd unit names.
Each new bot has an independent private data dir and a dedicated systemd instance.
Legacy BloodMoon AI continues in its unchanged service and installation directory.
"""
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import tempfile

BOT_ROOT = Path("/var/lib/opensim-ai-bridge/bots")
BOT_ID = re.compile(r"^[0-9a-f]{16}$")
MAX_BOTS = 16


class BotRegistryError(Exception):
    pass


def bot_path(bot_id):
    if not isinstance(bot_id, str) or not BOT_ID.fullmatch(bot_id):
        raise BotRegistryError("Invalid bot identifier")
    return BOT_ROOT / bot_id


def bot_unit(bot_id):
    bot_path(bot_id)  # validate, never accept an arbitrary unit name
    return f"opensim-ai-bridge@{bot_id}.service"


def instances():
    if not BOT_ROOT.is_dir():
        return []
    entries = []
    for entry in sorted(BOT_ROOT.iterdir()):
        if entry.is_dir() and BOT_ID.fullmatch(entry.name):
            entries.append(entry.name)
    return entries


def get_metadata(bot_id):
    p = bot_path(bot_id) / "appsettings.json"
    if p.is_symlink():
        raise BotRegistryError("Invalid bot configuration")
    doc = json.loads(p.read_text(encoding="utf-8"))
    grid = doc["Grid"]
    return {
        "id": bot_id,
        "firstName": grid["AvatarFirstName"],
        "lastName": grid["AvatarLastName"],
        "region": grid.get("StartLocation", {}).get("RegionName", ""),
    }


def validate_create(values):
    if not isinstance(values, dict) or set(values) != {"firstName", "lastName", "password", "region", "x", "y", "z"}:
        raise BotRegistryError("Invalid bot fields")
    for field, maximum in (("firstName", 32), ("lastName", 32), ("region", 80)):
        value = values[field]
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
            raise BotRegistryError("Invalid " + field)
        if any(ord(c) < 32 for c in value):
            raise BotRegistryError("Invalid characters in " + field)
    pw = values["password"]
    if not isinstance(pw, str) or not 1 <= len(pw) <= 256 or any(c in pw for c in ("\n", "\r", "\x00")):
        raise BotRegistryError("Invalid password")
    for field, hi in (("x", 256), ("y", 256), ("z", 4096)):
        if type(values[field]) is not int or not 0 <= values[field] <= hi:
            raise BotRegistryError("Invalid coordinate")
    return {key: value.strip() if key != "password" and isinstance(value, str) else value for key, value in values.items()}


def create_bot(values, legacy_install):
    values = validate_create(values)
    if not BOT_ROOT.is_dir():
        raise BotRegistryError("Bot storage missing; install multi-bot support first")
    if len(instances()) >= MAX_BOTS:
        raise BotRegistryError("Maximum number of bots reached")

    # Reuse the working grid login endpoint; credentials stay independent.
    legacy = json.loads((legacy_install / "appsettings.json").read_text(encoding="utf-8"))
    login_uri = legacy["Grid"]["LoginUri"]
    wanted = (values["firstName"].casefold(), values["lastName"].casefold())
    existing = (legacy["Grid"]["AvatarFirstName"].casefold(), legacy["Grid"]["AvatarLastName"].casefold())
    if wanted == existing:
        raise BotRegistryError("This avatar already runs as the main bot")
    for bot_id in instances():
        metadata = get_metadata(bot_id)
        if wanted == (metadata["firstName"].casefold(), metadata["lastName"].casefold()):
            raise BotRegistryError("This avatar is already registered")

    uid = legacy_install.stat().st_uid
    gid = legacy_install.stat().st_gid
    bot_id = secrets.token_hex(8)
    path = bot_path(bot_id)
    path.mkdir(mode=0o700)
    try:
        os.chown(path, uid, gid)
        cfg = {
            "Grid": {
                "LoginUri": login_uri,
                "AvatarFirstName": values["firstName"],
                "AvatarLastName": values["lastName"],
                "AvatarPasswordEnv": "OSAI_AVATAR_PASSWORD",
                "StartLocation": {"RegionName": values["region"], "Position": {"X": values["x"], "Y": values["y"], "Z": values["z"]}},
            },
            "Bot": {"EnableIM": True, "EnableLocalChat": True, "ReconnectEnabled": True},
        }
        # Exclusive creation with root-managed file ownership, no secret in stdout.
        for name, text in (("appsettings.json", json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"),
                           ("bot-password.txt", values["password"] + "\n")):
            file = path / name
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.chown(file, uid, gid)
            os.chmod(file, 0o600)
        (path / "data").mkdir(mode=0o700)
        os.chown(path / "data", uid, gid)
    except Exception:
        # Fail closed; clean up only files just created here.
        for name in ("appsettings.json", "bot-password.txt"):
            (path / name).unlink(missing_ok=True)
        (path / "data").rmdir() if (path / "data").exists() else None
        path.rmdir()
        raise

    # Start only this instance, never the legacy service.
    result = subprocess.run(["/usr/bin/systemctl", "enable", "--now", bot_unit(bot_id)],
                            text=True, capture_output=True, timeout=35)
    if result.returncode:
        return {"botId": bot_id, "started": False, "message": "Avatar registered, but the service failed to start"}
    return {"botId": bot_id, "started": True}
