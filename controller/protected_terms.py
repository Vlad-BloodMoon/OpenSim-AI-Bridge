"""Shared editable BloodMoon vocabulary for Azure-assisted knowledge lookup.

Only the root-owned local controller can update this file; the bot reads it
without credentials or a restart. Data never appears in the public web root.
"""
import json
import os
import re
import stat
import tempfile
from pathlib import Path

FILENAME = "knowledge-terms.json"
DOMAINS = ("grid", "roleplay", "marketplace", "handbook", "")
MAX_TERMS = 100
WORD = re.compile(r"^[^\x00-\x1f\x7f<>\{\}\[\]]{2,60}$")

# Shared defaults; editable once saved through the admin panel.
DEFAULTS = [
    {"term": "Grid", "aliases": "grille, griglia, grade, rejilla", "keywords": "grid, grille, bloodmoon", "domain": "grid"},
    {"term": "Freeland", "aliases": "Freelands", "keywords": "freeland, freelands, terrain, parcelle", "domain": "grid"},
    {"term": "HUD", "aliases": "HUDs", "keywords": "hud, huds", "domain": ""},
    {"term": "Hypergrid", "aliases": "HG", "keywords": "hypergrid", "domain": "handbook"},
    {"term": "OpenSim", "aliases": "OpenSimulator", "keywords": "opensim, opensimulator", "domain": "handbook"},
    {"term": "ROBUST", "aliases": "", "keywords": "robust", "domain": "handbook"},
    {"term": "Marketplace", "aliases": "Magic Box", "keywords": "marketplace, magic, box", "domain": "marketplace"},
    {"term": "BloodMoon Pack", "aliases": "", "keywords": "bloodmoon, pack, clan", "domain": "roleplay"},
    {"term": "Vital Liquid", "aliases": "", "keywords": "vital, liquid", "domain": "roleplay"},
]


class TermsError(Exception):
    pass


def _words(raw, maximum=12):
    if not isinstance(raw, str) or len(raw) > 900:
        raise TermsError("Invalid vocabulary text")
    tokens = [w.strip() for w in raw.split(",") if w.strip()]
    if len(tokens) > maximum or any(not WORD.fullmatch(w) for w in tokens):
        raise TermsError("Vocabulary values must be 2–60 printable characters")
    if len({w.casefold() for w in tokens}) != len(tokens):
        raise TermsError("Duplicate vocabulary variant")
    return tokens


def validate(record):
    if not isinstance(record, dict) or set(record) != {"term", "aliases", "keywords", "domain"}:
        raise TermsError("Invalid vocabulary entry")
    term = record["term"]
    if not isinstance(term, str) or not WORD.fullmatch(term.strip()):
        raise TermsError("Invalid vocabulary term")
    aliases = _words(record["aliases"])
    keywords = _words(record["keywords"], maximum=16)
    if not keywords:
        raise TermsError("At least one retrieval keyword is required")
    if record["domain"] not in DOMAINS:
        raise TermsError("Invalid knowledge category")
    return {"term": term.strip(), "aliases": ", ".join(aliases),
            "keywords": ", ".join(keywords), "domain": record["domain"]}


def config_path(install):
    return Path(install) / "config" / FILENAME


def read(install):
    path = config_path(install)
    if not path.exists():
        return [dict(x) for x in DEFAULTS]
    if path.is_symlink() or path.stat().st_size > 65536:
        raise TermsError("Vocabulary file invalid")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"entries"} or not isinstance(payload["entries"], list):
            raise TermsError("Vocabulary document invalid")
        if len(payload["entries"]) > MAX_TERMS:
            raise TermsError("Too many vocabulary entries")
        rows = [validate(x) for x in payload["entries"]]
        names = [r["term"].casefold() for r in rows]
        if len(set(names)) != len(names):
            raise TermsError("Duplicate vocabulary term")
        return rows
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        raise TermsError("Cannot read protected vocabulary") from exc


def _write(install, entries):
    path = config_path(install)
    directory = path.parent
    if not directory.is_dir() or directory.is_symlink() or path.is_symlink():
        raise TermsError("Vocabulary config directory invalid")
    if len(entries) > MAX_TERMS:
        raise TermsError("Vocabulary limit reached")
    owner = (Path(install) / "appsettings.json").stat()
    descriptor, temporary = tempfile.mkstemp(prefix=".knowledge-terms-", dir=str(directory))
    try:
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, owner.st_uid, owner.st_gid)
        with os.fdopen(descriptor, "w", encoding="utf-8") as out:
            json.dump({"entries": entries}, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def upsert(install, values):
    if not isinstance(values, dict) or set(values) != {"previous", "term", "aliases", "keywords", "domain"}:
        raise TermsError("Invalid vocabulary command")
    previous = values["previous"]
    if not isinstance(previous, str):
        raise TermsError("Invalid previous name")
    item = validate({k: values[k] for k in ("term", "aliases", "keywords", "domain")})
    entries = read(install)
    found = next((i for i, e in enumerate(entries) if e["term"].casefold() == previous.casefold()), None)
    if previous and found is None:
        raise TermsError("Term not found; reload the page")
    if any(e["term"].casefold() == item["term"].casefold() and i != found
           for i, e in enumerate(entries)):
        raise TermsError("This term already exists")
    if found is not None:
        entries[found] = item
    else:
        entries.append(item)
    _write(install, entries)
    return {"saved": True, "count": len(entries)}


def delete(install, values):
    if not isinstance(values, dict) or set(values) != {"term"} or not isinstance(values["term"], str):
        raise TermsError("Invalid vocabulary deletion")
    old = read(install)
    rows = [item for item in old if item["term"].casefold() != values["term"].casefold()]
    if len(rows) == len(old):
        raise TermsError("Unknown term")
    _write(install, rows)
    return {"deleted": True, "count": len(rows)}
