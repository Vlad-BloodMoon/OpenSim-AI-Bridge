#!/usr/bin/env python3
"""Read-only public BloodMoon HTML crawler and SQLite FTS5 index.

Only crawl explicit approved site areas; refuse redirects and private endpoints.
No network requests are made by the bot or when searching.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
from html.parser import HTMLParser
import json
import re
import sqlite3
import subprocess
import tempfile
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode, quote, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

SOURCES = {
    "grid": "https://bloodmoonpack.com/grid/",
    "roleplay": "https://bloodmoonpack.com/",
    "marketplace": "https://bloodmoonpack.com/Marketplace/",
    "handbook": "https://bloodmoonpack.com/OpenSim_Handbook/",
}
# No unrelated site directories, privileged pages, user profiles or carts.
PRIVATE_PARTS = (
    "admin", "login", "logout", "signin", "signup", "register",
    "create-account", "reset-password", "password", "profile",
    "account", "checkout", "cart", "order", "payment", "invoice",
    "upload", "delete", "edit", "manage", "manager", "dashboard",
    "api", "callback", "webhook", "phpmyadmin", "search", "session",
    "my-", "user", "player", "member", "stats", "attack", "souls",
)
IGNORE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".css", ".js", ".json", ".xml", ".zip", ".oar", ".iar", ".pdf", ".mp4", ".woff", ".ttf")
MAX_RESPONSE_BYTES = 8_000_000
MAX_PDF_BYTES = 12_000_000
MAX_PDF_PAGES = 60
MAX_SITE_PAGES = 2500
MAX_PDF_DOCUMENTS = 300
MAX_TEXT_CHARS = 600_000
MAX_CHUNK_CHARS = 1300
DEFAULT_DB = Path("/home/louna49400/OpenSim-AI-Bridge/data/bloodmoon_knowledge.db")
LOCAL_ROOT = Path("/var/www/BloodMoon/AI_Knowledge")
LOCAL_CATEGORIES = ("marketplace", "opensim", "grid_bloodmoon", "roleplay_bloodmoon")
LOCAL_PREFIX = "local_"
FILES_PDF_ROOT = Path("/var/www/BloodMoon/files")
FILES_PDF_PREFIX = "https://bloodmoonpack.com/files/"
# No file-count or page-count limit. Individual PDF resource caps are safety limits.
MAX_FILES_PDF_BYTES = 200_000_000
MAX_LOCAL_FILES = 500
MAX_LOCAL_FILE_BYTES = 256_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("HTTP redirect refused: review the source URL")


class PageText(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    SKIP = {"script", "style", "noscript", "svg", "iframe", "form", "nav", "footer",
            "header", "aside", "template"}
    # Avoid indexing dynamic region directories, personal feeds and huge listings.
    SKIP_LABELS = {"region-list", "regions-list", "latest-attacks", "latest_attacks",
                   "grid-map", "map-region-list", "maptiles", "leaderboard"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts = []
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            # Navigation menu links are authoritative discovery targets,
            # even though menu text itself is excluded from the search index.
            self.links.append(attrs["href"])
        if self.skip_depth:
            if tag not in self.VOID:
                self.skip_depth += 1
        elif tag in self.SKIP or any(k in (" " + attrs.get("id", "") + " " + attrs.get("class", "") + " ").lower() for k in self.SKIP_LABELS):
            self.skip_depth = 1
        elif tag == "title":
            self.title_depth += 1
        elif tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "section", "article", "br", "tr"}:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag not in self.VOID:
                self.skip_depth -= 1
        elif tag == "title" and self.title_depth:
            self.title_depth -= 1

    def handle_data(self, data):
        if self.skip_depth or not data.strip():
            return
        if self.title_depth:
            self.title_parts.append(data.strip())
        else:
            self.parts.append(data.strip())

    def extract(self):
        title = " ".join(self.title_parts).strip()[:200]
        lines = [re.sub(r"\s+", " ", line).strip() for line in "".join(self.parts).splitlines()]
        good = []
        for line in lines:
            # A compact region map or unstructured numeric dump is not useful RAG evidence.
            if not line or (len(line) > 220 and len(re.findall(r"\d", line)) / len(line) > .23):
                continue
            good.append(line)
        return title, "\n".join(good)[:MAX_TEXT_CHARS]


def canonical(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "bloodmoonpack.com" or parsed.username or parsed.password or parsed.port:
        return None
    path = parsed.path
    if "//" in path or "\\" in path or "/." in path or len(path) > 180:
        return None
    # Only language switches are retained; no freeform query strings, IDs or pagination.
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(k != "lang" or v.lower() not in {"en", "fr", "es", "de", "pt", "it"} for k, v in query):
        return None
    lang = query[0][1].lower() if query else ""
    return urlunsplit(("https", "bloodmoonpack.com", path, urlencode({"lang": lang}) if lang else "", ""))


def approved(source, url):
    # This explicit public file subtree is read from local disk only by import-files-pdfs.
    # Existing grid/handbook source labels ensure the deployed .NET retriever can use it
    # without an avatar binary update. No other site directories become indexable.
    if source in ("grid", "handbook") and url.startswith(FILES_PDF_PREFIX):
        parsed = urlsplit(url)
        raw = unquote(parsed.path)
        segments = raw.split("/")
        if (parsed.scheme == "https" and parsed.netloc == "bloodmoonpack.com"
                and not parsed.query and not parsed.fragment
                and len(parsed.path) <= 1024 and raw.startswith("/files/")
                and segments[0:2] == ["", "files"]
                and all(p and p not in (".", "..") and "\\\\" not in p for p in segments[2:])
                and raw.lower().endswith(".pdf")
                and quote(raw, safe="/") == parsed.path):
            return url
        return None
    if source.startswith(LOCAL_PREFIX):
        category = source[len(LOCAL_PREFIX):]
        parsed = urlsplit(url)
        name = parsed.path.lstrip("/")
        if (category in LOCAL_CATEGORIES and parsed.scheme == "knowledge" and parsed.netloc == category and \
                re.fullmatch(r"[a-zA-Z0-9À-ÿ_.-]{1,100}\.txt", name) and \
                not name.startswith(".") and not parsed.query and not parsed.fragment):
            return url
        return None
    value = canonical(url)
    if not value or source not in SOURCES:
        return None
    path = urlsplit(value).path
    is_guide_pdf = (source == "roleplay" and path.startswith("/Download/GUIDE/") and path.lower().endswith(".pdf"))
    if path.lower().endswith(IGNORE_EXT) and not is_guide_pdf:
        return None
    if is_guide_pdf:
        return value if not urlsplit(value).query else None
    pieces = [p.lower().replace("_", "-") for p in path.strip("/").split("/") if p]
    if any(any(p == x or p.startswith(x + "-") or p.startswith(x + ".") for x in PRIVATE_PARTS) for p in pieces):
        return None
    if source == "grid":
        if path.lower() in {"/grid/join.php", "/grid/events/add.php", "/grid/events/my-events.php"}:
            return None
        return value if path.startswith("/grid/") else None
    if source == "marketplace":
        # Skip personalized endpoints that redirect to a login page.
        if path.lower() in {"/marketplace/favorites.php", "/marketplace/seller.php"}:
            return None
        return value if path.startswith("/Marketplace/") else None
    if source == "handbook":
        return value if path.startswith("/OpenSim_Handbook/") else None
    # RP home and documented public informational pages only.
    if path == "/" or path.startswith("/roleplay/pages/"):
        return value
    return None


def chunks(text):
    result, buffer = [], ""
    for paragraph in text.split("\n"):
        for i in range(0, len(paragraph), MAX_CHUNK_CHARS):
            part = paragraph[i:i + MAX_CHUNK_CHARS]
            if buffer and len(buffer) + len(part) + 1 > MAX_CHUNK_CHARS:
                result.append(buffer)
                buffer = ""
            buffer = (buffer + "\n" + part).strip()
    if buffer:
        result.append(buffer)
    return result


def connect(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    # v2 tables intentionally coexist with v1's single-document tables.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_pages (
            url TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL,
            sha256 TEXT NOT NULL, indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_passages
        USING fts5(source UNINDEXED, url UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')
    """)
    return conn


def store(conn, source, url, title, text):
    if approved(source, url) != url:
        raise ValueError("Unapproved knowledge URL")
    if len(text.strip()) < (20 if source.startswith(LOCAL_PREFIX) else 80):
        raise ValueError("Too little useful text to index")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    previous = conn.execute("SELECT sha256 FROM knowledge_pages WHERE url=?", (url,)).fetchone()
    if previous and previous[0] == digest:
        return "unchanged", 0
    parts = chunks(text)
    with conn:
        conn.execute("DELETE FROM knowledge_passages WHERE url=?", (url,))
        conn.executemany(
            "INSERT INTO knowledge_passages(source,url,title,body) VALUES (?,?,?,?)",
            ((source, url, title or source, part) for part in parts)
        )
        conn.execute("""
            INSERT INTO knowledge_pages(url,source,title,sha256,indexed_at)
            VALUES (?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(url) DO UPDATE SET source=excluded.source,title=excluded.title,
              sha256=excluded.sha256,indexed_at=CURRENT_TIMESTAMP
        """, (url, source, title or source, digest))
    return "indexed", len(parts)


def download(source, url):
    if approved(source, url) != url:
        raise ValueError("Unapproved URL")
    opener = build_opener(NoRedirect())
    request = Request(url, headers={"User-Agent": "BloodMoonKnowledgeIndexer/0.2 (admin-managed)",
                                   "Accept": "text/html"})
    with opener.open(request, timeout=12) as response:
        if response.geturl() != url:
            raise ValueError("Unexpected final URL")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("Unexpected content type")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Page too large")
        charset = response.headers.get_content_charset() or "utf-8"
        if charset.lower().replace("_", "-") not in {"utf-8", "iso-8859-1", "windows-1252"}:
            raise ValueError("Unexpected encoding")
        return raw.decode(charset, errors="replace")


def download_pdf(source, url):
    if approved(source, url) != url or not urlsplit(url).path.startswith("/Download/GUIDE/"):
        raise ValueError("PDF outside approved Roleplay guide")
    request = Request(url, headers={"User-Agent": "BloodMoonKnowledgeIndexer/0.3 (admin-managed)",
                                   "Accept": "application/pdf"})
    with build_opener(NoRedirect()).open(request, timeout=25) as response:
        if response.geturl() != url or response.headers.get_content_type() != "application/pdf":
            raise ValueError("Unexpected PDF response type or URL")
        raw = response.read(MAX_PDF_BYTES + 1)
        if len(raw) > MAX_PDF_BYTES or not raw.startswith(b"%PDF-"):
            raise ValueError("PDF too large or malformed")
        return raw


def extract_pdf(pdf_bytes):
    """pdftotext / pdfinfo from poppler-utils; never invoke shells or OCR."""
    with tempfile.TemporaryDirectory(prefix="bm-guide-") as folder:
        path = Path(folder) / "guide.pdf"
        path.write_bytes(pdf_bytes)
        info = subprocess.run(["/usr/bin/pdfinfo", str(path)], capture_output=True,
                              text=True, timeout=15, check=False)
        if info.returncode:
            raise ValueError("Cannot inspect guide PDF")
        pages = re.search(r"^Pages:\s*(\d+)", info.stdout, re.MULTILINE)
        if not pages or int(pages.group(1)) > MAX_PDF_PAGES:
            raise ValueError("Guide PDF exceeds page limit")
        result = subprocess.run(["/usr/bin/pdftotext", "-layout", "-enc", "UTF-8",
                                 str(path), "-"], capture_output=True, text=True,
                                timeout=30, check=False)
        if result.returncode:
            raise ValueError("Could not extract guide PDF text")
        # No OCR; scanned/image-only documents need manual review.
        text = re.sub(r"[ \\t]+", " ", result.stdout).replace("\\f", "\\n")
        return text[:MAX_TEXT_CHARS]


def parse_page(markup):
    parser = PageText()
    parser.feed(markup)
    title, text = parser.extract()
    return title, text, parser.links


def crawl(conn, source, max_pages=600, delay=.15):
    pending = deque([SOURCES[source]])
    visited = set()
    pdf_pending = deque()
    pdf_visited = set()
    counts = {"indexed": 0, "unchanged": 0, "errors": 0, "pages": 0, "pdfs": 0, "passages": 0}
    while pending and len(visited) < max_pages:
        url = pending.popleft()
        if url in visited or approved(source, url) != url:
            continue
        visited.add(url)
        try:
            title, text, links = parse_page(download(source, url))
            state, n = store(conn, source, url, title, text)
            counts[state] += 1
            counts["passages"] += n
            print(f"  {state}: {url} [{len(text)} chars]", flush=True)
            for href in links:
                target = approved(source, canonical(urljoin(url, href)) or "")
                if not target:
                    continue
                if target.lower().split("?")[0].endswith(".pdf"):
                    # PDF links from approved Roleplay guide page only.
                    if source == "roleplay" and urlsplit(url).path == "/roleplay/pages/guide.php" and target not in pdf_visited and target not in pdf_pending:
                        pdf_pending.append(target)
                elif target not in visited and target not in pending:
                    pending.append(target)
        except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
            counts["errors"] += 1
            print(f"  ERROR {url}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        counts["pages"] += 1
        if pending and delay:
            time.sleep(delay)
    for url in list(pdf_pending)[:MAX_PDF_DOCUMENTS]:
        if url in pdf_visited:
            continue
        pdf_visited.add(url)
        try:
            pdf_text = extract_pdf(download_pdf(source, url))
            title = Path(urlsplit(url).path).stem.replace("_", " ")
            state, n = store(conn, source, url, title, pdf_text)
            counts[state] += 1
            counts["passages"] += n
            print(f"  {state} PDF: {url} [{len(pdf_text)} chars]", flush=True)
        except (HTTPError, URLError, OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
            counts["errors"] += 1
            print(f"  PDF ERROR {url}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        counts["pdfs"] += 1
        if delay:
            time.sleep(delay)
    return counts


def import_files_pdfs(conn, root=FILES_PDF_ROOT):
    """Incrementally index all textual PDF pages below the approved public /files directory.

    Files are read from disk (never HTTP); the index uses source='handbook' for
    Physics_Engine and source='grid' elsewhere, so the deployed bot reads them.
    PDF count and page count are not capped. Unsafe symlinks are never followed.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("PDF directory missing or symlinked: " + str(root))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_files_pdf (
            url TEXT PRIMARY KEY,
            file_sha256 TEXT NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    counters = {"files": 0, "indexed": 0, "unchanged": 0, "deleted": 0,
                "errors": 0, "pages": 0}
    found = set()
    # Walk only real subdirectories. Ignore symlinked files and subdirectories.
    for base, dirs, names in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(base) / d).is_symlink())
        for filename in sorted(names):
            if not filename.lower().endswith(".pdf"):
                continue
            file = Path(base) / filename
            if file.is_symlink() or not file.is_file():
                continue
            relative = file.relative_to(root)
            # Reject paths that could be ambiguous if published as HTTPS URLs.
            if any(not p or p in (".", "..") or "\\\\" in p or "\\x00" in p
                   for p in relative.parts):
                continue
            url = FILES_PDF_PREFIX + quote(relative.as_posix(), safe="/")
            source = "handbook" if relative.parts[0].lower() == "physics_engine" else "grid"
            if approved(source, url) != url:
                counters["errors"] += 1
                print("  INVALID PDF PATH: " + str(relative), file=sys.stderr)
                continue
            found.add(url)
            counters["files"] += 1
            try:
                size = file.stat().st_size
                if not 5 <= size <= MAX_FILES_PDF_BYTES:
                    raise ValueError("PDF size outside safety limits")
                digest = hashlib.sha256()
                with file.open("rb") as stream:
                    if not stream.read(5) == b"%PDF-":
                        raise ValueError("Not a PDF file")
                    stream.seek(0)
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                sha = digest.hexdigest()
                previous = conn.execute(
                    "SELECT file_sha256 FROM knowledge_files_pdf WHERE url=?", (url,)
                ).fetchone()
                indexed = conn.execute(
                    "SELECT 1 FROM knowledge_pages WHERE url=? AND source=?", (url, source)
                ).fetchone()
                if previous and previous[0] == sha and indexed:
                    counters["unchanged"] += 1
                    continue
                proc = subprocess.run(
                    ["/usr/bin/pdftotext", "-layout", "-enc", "UTF-8", str(file), "-"],
                    capture_output=True, timeout=180, check=False
                )
                if proc.returncode:
                    raise ValueError("pdftotext failed (possibly encrypted or malformed)")
                # Page separators are kept as explicit headings; no page is skipped.
                pages = proc.stdout.decode("utf-8", errors="replace").split("\\f")
                if pages and not pages[-1].strip():
                    pages.pop()
                text = "\\n".join(
                    "Page " + str(i) + "\\n" + page.strip()
                    for i, page in enumerate(pages, 1) if page.strip()
                )
                if not text.strip():
                    raise ValueError("No extractable PDF text (scanned/image-only?)")
                title = relative.stem.replace("_", " ").replace("-", " ")
                # Store uses FTS5 passages; only this URL is replaced, all other
                # website, roleplay PDFs and curated TXT entries are untouched.
                state, _ = store(conn, source, url, title, text)
                with conn:
                    conn.execute("""
                        INSERT INTO knowledge_files_pdf(url,file_sha256,indexed_at)
                        VALUES (?,?,CURRENT_TIMESTAMP)
                        ON CONFLICT(url) DO UPDATE SET
                        file_sha256=excluded.file_sha256,indexed_at=CURRENT_TIMESTAMP
                    """, (url, sha))
                counters["indexed" if state == "indexed" else "unchanged"] += 1
                counters["pages"] += len(pages)
                print("  " + state + ": " + str(relative)
                      + " [" + str(len(pages)) + " pages]", flush=True)
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                counters["errors"] += 1
                print("  PDF ERROR " + str(relative) + ": " + str(exc),
                      file=sys.stderr, flush=True)
    # Prune only documents previously indexed by this importer, after a fully
    # successful walk. A transient extraction error retains the previous entry.
    old = [u for (u,) in conn.execute("SELECT url FROM knowledge_files_pdf")]
    with conn:
        for url in old:
            if url in found:
                continue
            conn.execute("DELETE FROM knowledge_passages WHERE url=?", (url,))
            conn.execute("DELETE FROM knowledge_pages WHERE url=?", (url,))
            conn.execute("DELETE FROM knowledge_files_pdf WHERE url=?", (url,))
            counters["deleted"] += 1
    return counters


def import_local(conn, root=LOCAL_ROOT):
    """Index curated UTF-8 notes. No symlink traversal, network, or web publishing."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Local knowledge folder missing or symlinked")
    found = set()
    counters = {"indexed": 0, "unchanged": 0, "deleted": 0, "files": 0}
    for category in LOCAL_CATEGORIES:
        folder = root / category
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Missing or unsafe local category: " + category)
        for file in sorted(folder.iterdir()):
            if file.suffix.lower() != ".txt" or file.name.startswith("."):
                continue
            if file.is_symlink() or not file.is_file():
                raise ValueError("Unsafe local text file: " + category)
            if not re.fullmatch(r"[a-zA-Z0-9À-ÿ_.-]{1,100}\.txt", file.name):
                raise ValueError("Invalid local text filename: " + file.name)
            if file.stat().st_size > MAX_LOCAL_FILE_BYTES:
                raise ValueError("Local text file exceeds size limit: " + file.name)
            if counters["files"] >= MAX_LOCAL_FILES:
                raise ValueError("Too many local knowledge files")
            contents = file.read_text(encoding="utf-8-sig")
            # Ignore template/empty files; they are not useful knowledge.
            if len(contents.strip()) < 20:
                continue
            source = LOCAL_PREFIX + category
            url = "knowledge://" + category + "/" + file.name
            title = file.stem.replace("-", " ").replace("_", " ")
            result, _ = store(conn, source, url, title, contents)
            counters[result] += 1
            counters["files"] += 1
            found.add(url)
    # Remove local entries when their TXT file has been deleted.
    # This does not touch the separately crawled public HTML/PDF data.
    old = conn.execute("SELECT url FROM knowledge_pages WHERE source LIKE 'local_%'").fetchall()
    with conn:
        for (url,) in old:
            if url in found:
                continue
            conn.execute("DELETE FROM knowledge_passages WHERE url=?", (url,))
            conn.execute("DELETE FROM knowledge_pages WHERE url=?", (url,))
            counters["deleted"] += 1
    return counters


def safe_search(conn, query, count=5):
    tokens = re.findall(r"[^\W_]{2,}", query.lower(), flags=re.UNICODE)[:10]
    if not tokens:
        return []
    expression = " OR ".join('"' + word.replace('"', '""') + '"' for word in tokens)
    rows = conn.execute("""
        SELECT source, url, title, substr(body,1,450)
        FROM knowledge_passages WHERE knowledge_passages MATCH ?
        ORDER BY bm25(knowledge_passages) LIMIT ?
    """, (expression, count)).fetchall()
    return [dict(zip(["source", "url", "title", "excerpt"], row)) for row in rows]


def main():
    parser = argparse.ArgumentParser(description="BloodMoon public documentation crawler")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="action", required=True)
    grab = sub.add_parser("import", help="Crawl approved public HTML links")
    grab.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    grab.add_argument("--max-pages", type=int, default=600, help="Maximum HTML pages per source, 1 to 2500")
    fixture = sub.add_parser("import-html", help="Offline local HTML fixture")
    fixture.add_argument("--source", required=True, choices=list(SOURCES))
    fixture.add_argument("--file", type=Path, required=True)
    sub.add_parser("status")
    local_cmd = sub.add_parser("import-local", help="Index curated UTF-8 TXT files without network")
    local_cmd.add_argument("--root", type=Path, default=LOCAL_ROOT)
    files_cmd = sub.add_parser("import-files-pdfs", help="Incremental recursive index of public /files PDFs")
    files_cmd.add_argument("--root", type=Path, default=FILES_PDF_ROOT)
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.action == "import":
            if not 1 <= args.max_pages <= MAX_SITE_PAGES:
                parser.error("--max-pages must be between 1 and 2500")
            failures = 0
            for source in SOURCES if args.source == "all" else [args.source]:
                print(f"Indexing {source}:", flush=True)
                stats = crawl(conn, source, max_pages=args.max_pages)
                failures += stats["errors"]
                print(f"{source}: {json.dumps(stats)}", flush=True)
            return 1 if failures else 0
        if args.action == "import-html":
            title, text, _ = parse_page(args.file.read_text(encoding="utf-8"))
            print(store(conn, args.source, SOURCES[args.source], title, text))
        elif args.action == "import-local":
            print(json.dumps(import_local(conn, args.root), ensure_ascii=False, indent=2))
        elif args.action == "import-files-pdfs":
            result = import_files_pdfs(conn, args.root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result["errors"] else 0
        elif args.action == "status":
            rows = conn.execute("""
                SELECT source,count(*),sum((SELECT count(*) FROM knowledge_passages p WHERE p.url=d.url))
                FROM knowledge_pages d GROUP BY source ORDER BY source
            """).fetchall()
            print(json.dumps([dict(zip(["source", "pages", "passages"], row)) for row in rows],
                             ensure_ascii=False, indent=2))
        elif args.action == "search":
            print(json.dumps(safe_search(conn, args.query, max(1, min(args.limit, 10))),
                             ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
