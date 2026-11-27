"""Opt-in V2 catalog refresh; independent of OpenSim IM and the V1 router.

No background service is started here. The only remote request is to a pinned
HTTPS catalog host, without cookies, tokens, authorization or redirects.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from catalog_models import CatalogError, normalize_catalog

SOURCE_URL = "https://free-llm.com/catalog.json"
# Upstream publishes the same v2 schema as a daily snapshot in its own repository.
MIRROR_URL = "https://raw.githubusercontent.com/nejib1/Free-LLM/main/router/catalog.snapshot.json"
MAX_DOWNLOAD_BYTES = 2_000_000
MAX_CACHE_BYTES = 2_000_000


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CatalogError("Catalog redirects are not permitted")


def _download_pinned(url):
    if url not in (SOURCE_URL, MIRROR_URL):
        raise CatalogError("Unapproved catalog URL")
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "BloodMoonAI-Catalog/1.0"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=10) as response:
        if response.status != 200:
            raise CatalogError("Catalog endpoint returned a non-success status")
        if int(response.headers.get("Content-Length", "0")) > MAX_DOWNLOAD_BYTES:
            raise CatalogError("Catalog response is too large")
        raw = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(raw) > MAX_DOWNLOAD_BYTES:
            raise CatalogError("Catalog response exceeds download limit")
        return raw


def download_catalog():
    """Use the upstream HTTPS endpoint, then its official GitHub snapshot.

    Some cloud/datacenter IPs receive HTTP 403 from the website; the mirror is
    published in the SAME upstream GitHub repository, not a third-party proxy.
    Both payloads are validated identically before cache replacement.
    """
    errors = []
    for url in (SOURCE_URL, MIRROR_URL):
        try:
            return _download_pinned(url)
        except (CatalogError, urllib.error.URLError, OSError) as exc:
            errors.append(type(exc).__name__)
    raise CatalogError("All approved catalog sources failed: " + ", ".join(errors))


def _validate_path(path):
    path = Path(path)
    if not path.parent.is_dir() or path.parent.is_symlink() or path.is_symlink():
        raise CatalogError("Unsafe or missing cache directory")
    if path.exists() and not path.is_file():
        raise CatalogError("Unsafe cache file")
    return path


def refresh(cache_path, fetcher=download_catalog):
    """Commit a validated snapshot atomically; on any error keep old cache."""
    path = _validate_path(cache_path)
    raw = fetcher()
    if not isinstance(raw, bytes) or len(raw) > MAX_DOWNLOAD_BYTES:
        raise CatalogError("Invalid catalog payload size")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CatalogError("Invalid UTF-8 JSON catalog") from exc
    snapshot = normalize_catalog(payload)
    data = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_CACHE_BYTES:
        raise CatalogError("Normalized catalog exceeds cache limit")
    fd, tmp = tempfile.mkstemp(prefix=".catalog-", dir=str(path.parent))
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {"models": len(snapshot["models"]), "generatedAtUtc": snapshot["generatedAtUtc"]}


def read_cache(cache_path):
    path = _validate_path(cache_path)
    if not path.is_file() or path.stat().st_size > MAX_CACHE_BYTES:
        return None
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 2:
            return None
        if not isinstance(snapshot.get("models"), list):
            return None
        return snapshot
    except (UnicodeError, OSError, ValueError):
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explicit refresh of read-only AI model catalog")
    parser.add_argument("--cache", type=Path, required=True,
                        help="Dedicated cache file, outside Web root and existing bot data")
    args = parser.parse_args()
    try:
        print(json.dumps(refresh(args.cache), ensure_ascii=False))
    except (CatalogError, OSError, urllib.error.URLError) as exc:
        parser.exit(1, "Catalog refresh skipped; previous cache left unchanged: " + str(exc) + "\n")
