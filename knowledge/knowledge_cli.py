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
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
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
MAX_RESPONSE_BYTES = 1_500_000
MAX_TEXT_CHARS = 180_000
MAX_CHUNK_CHARS = 1300
DEFAULT_DB = Path("/home/louna49400/OpenSim-AI-Bridge/data/bloodmoon_knowledge.db")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("HTTP redirect refused: review the source URL")


class PageText(HTMLParser):
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
        if tag == "a" and not self.skip_depth and attrs.get("href"):
            self.links.append(attrs["href"])
        if self.skip_depth:
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
    value = canonical(url)
    if not value or source not in SOURCES:
        return None
    path = urlsplit(value).path
    if path.lower().endswith(IGNORE_EXT):
        return None
    pieces = [p.lower().replace("_", "-") for p in path.strip("/").split("/") if p]
    if any(any(p == x or p.startswith(x + "-") or p.startswith(x + ".") for x in PRIVATE_PARTS) for p in pieces):
        return None
    if source == "grid":
        return value if path.startswith("/grid/") else None
    if source == "marketplace":
        # Catalog help and public descriptions only; never checkout or account functions.
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
    if len(text.strip()) < 80:
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


def parse_page(markup):
    parser = PageText()
    parser.feed(markup)
    title, text = parser.extract()
    return title, text, parser.links


def crawl(conn, source, max_pages=80, delay=.15):
    pending = deque([SOURCES[source]])
    visited = set()
    counts = {"indexed": 0, "unchanged": 0, "errors": 0, "pages": 0, "passages": 0}
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
            # Link discovery only from already-approved public HTML pages.
            for href in links:
                target = approved(source, canonical(urljoin(url, href)) or "")
                if target and target not in visited and target not in pending:
                    pending.append(target)
        except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
            counts["errors"] += 1
            print(f"  ERROR {url}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        counts["pages"] += 1
        if pending and delay:
            time.sleep(delay)
    return counts


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
    grab.add_argument("--max-pages", type=int, default=80, help="Maximum HTML pages per source, 1 to 120")
    fixture = sub.add_parser("import-html", help="Offline local HTML fixture")
    fixture.add_argument("--source", required=True, choices=list(SOURCES))
    fixture.add_argument("--file", type=Path, required=True)
    sub.add_parser("status")
    find = sub.add_parser("search")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.action == "import":
            if not 1 <= args.max_pages <= 120:
                parser.error("--max-pages must be between 1 and 120")
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
