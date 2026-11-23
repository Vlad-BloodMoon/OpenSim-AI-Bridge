#!/usr/bin/env python3
"""BloodMoon knowledge index prototype: four approved public landing pages.

Only invoked by the administrator; no bot or Web integration at this stage.
Requires Python >=3.10 with SQLite FTS5. Uses standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import sqlite3
from pathlib import Path
import re
import sys
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

SOURCES = {
    "grid": "https://bloodmoonpack.com/grid/",
    "roleplay": "https://bloodmoonpack.com/",
    "marketplace": "https://bloodmoonpack.com/Marketplace/",
    "handbook": "https://bloodmoonpack.com/OpenSim_Handbook/",
}
MAX_RESPONSE_BYTES = 1_500_000
MAX_TEXT_CHARS = 180_000
MAX_CHUNK_CHARS = 1300
DEFAULT_DB = Path("/home/louna49400/OpenSim-AI-Bridge/data/bloodmoon_knowledge.db")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("HTTP redirect refused: update approved URL after review")


class PageText(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "iframe", "form", "nav", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if self.skip_depth:
            self.skip_depth += 1
        elif tag in self.SKIP:
            self.skip_depth = 1
        elif tag == "title":
            self.title_depth += 1
        elif tag in {"p", "div", "h1", "h2", "h3", "li", "section", "article", "br"}:
            self.parts.append("\n")

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
        text = "\n".join(line for line in lines if line)[:MAX_TEXT_CHARS]
        return title, text


def chunks(text: str):
    """Prefer paragraph boundaries and cap the size of every FTS entry."""
    result = []
    buffer = ""
    for paragraph in text.split("\n"):
        if not paragraph:
            continue
        for part in (paragraph[i:i + MAX_CHUNK_CHARS] for i in range(0, len(paragraph), MAX_CHUNK_CHARS)):
            if buffer and len(buffer) + len(part) + 1 > MAX_CHUNK_CHARS:
                result.append(buffer)
                buffer = ""
            buffer = (buffer + "\n" + part).strip()
    if buffer:
        result.append(buffer)
    return result


def connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS passages
        USING fts5(source UNINDEXED, url UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')
    """)
    return conn


def store(conn, source: str, title: str, text: str):
    if source not in SOURCES:
        raise ValueError("Unknown source")
    if not text.strip():
        raise ValueError("Empty page content, refusing to erase previous index")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    previous = conn.execute("SELECT sha256 FROM documents WHERE source=?", (source,)).fetchone()
    if previous is not None and previous[0] == digest:
        return "unchanged", 0
    parts = chunks(text)
    with conn:
        conn.execute("DELETE FROM passages WHERE source=?", (source,))
        conn.executemany(
            "INSERT INTO passages(source,url,title,body) VALUES (?,?,?,?)",
            ((source, SOURCES[source], title or source, part) for part in parts)
        )
        conn.execute("""
            INSERT INTO documents(source,url,title,sha256,indexed_at)
            VALUES (?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(source) DO UPDATE SET
              title=excluded.title,sha256=excluded.sha256,indexed_at=CURRENT_TIMESTAMP
        """, (source, SOURCES[source], title or source, digest))
    return "indexed", len(parts)


def download(source):
    url = SOURCES[source]  # Fixed exact URL only. Never fetch user-supplied URLs.
    opener = build_opener(NoRedirect())
    request = Request(url, headers={"User-Agent": "BloodMoonKnowledgeIndexer/0.1 (+admin-managed)",
                                    "Accept": "text/html"})
    with opener.open(request, timeout=12) as response:
        if response.geturl() != url:
            raise ValueError("Unexpected final URL")
        content_type = response.headers.get_content_type()
        if content_type != "text/html":
            raise ValueError(f"Unexpected content type: {content_type}")
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
    return parser.extract()


def safe_search(conn, query, count=5):
    # Tokenize user text instead of allowing arbitrary FTS query syntax.
    tokens = re.findall(r"[^\W_]{2,}", query.lower(), flags=re.UNICODE)[:10]
    if not tokens:
        return []
    expression = " OR ".join('"' + word.replace('"', '""') + '"' for word in tokens)
    result = conn.execute("""
        SELECT source, url, title, substr(body,1,450) AS excerpt
        FROM passages WHERE passages MATCH ?
        ORDER BY bm25(passages) LIMIT ?
    """, (expression, count)).fetchall()
    return [{"source": a, "url": b, "title": c, "excerpt": d} for a, b, c, d in result]


def main():
    parser = argparse.ArgumentParser(description="BloodMoon offline knowledge index prototype")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="action", required=True)
    grab = sub.add_parser("import", help="Fetch approved public landing pages")
    grab.add_argument("--source", choices=[*SOURCES, "all"], default="all")
    fixture = sub.add_parser("import-html", help="Import administrator-reviewed local HTML for offline tests")
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
            errors = 0
            for source in (SOURCES if args.source == "all" else [args.source]):
                try:
                    title, text = parse_page(download(source))
                    state, n = store(conn, source, title, text)
                    print(f"{source}: {state}, passages={n}, characters={len(text)}")
                except (HTTPError, URLError, OSError, ValueError, UnicodeError) as exc:
                    errors += 1
                    print(f"{source}: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1 if errors else 0
        if args.action == "import-html":
            html = args.file.read_text(encoding="utf-8")
            title, text = parse_page(html)
            state, n = store(conn, args.source, title, text)
            print(f"{args.source}: {state}, passages={n}")
        elif args.action == "status":
            rows = conn.execute("""
                SELECT d.source,d.url,d.title,d.indexed_at,
                    (SELECT count(*) FROM passages p WHERE p.source=d.source)
                FROM documents d ORDER BY d.source
            """).fetchall()
            print(json.dumps([dict(zip(["source","url","title","indexed_at","passages"], row))
                              for row in rows], ensure_ascii=False, indent=2))
        elif args.action == "search":
            print(json.dumps(safe_search(conn, args.query, max(1, min(args.limit, 10))),
                             ensure_ascii=False, indent=2))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
