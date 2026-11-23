"""Offline regression tests: no network access, no grid service required."""
import importlib.util
from pathlib import Path
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
import unittest

MODULE = Path(__file__).resolve().parents[1] / "knowledge" / "knowledge_cli.py"
spec = importlib.util.spec_from_file_location("bloodmoon_knowledge_cli", MODULE)
kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb)


class KnowledgeTests(unittest.TestCase):
    def test_parse_and_search(self):
        html = ('<html><head><title>BloodMoon RP</title><script>SECRET</script></head>'
                '<body><nav><a href="/roleplay/pages/guide.php?lang=fr">Guide RP</a>Administration privee</nav><main>'
                '<h1>Vampires et malediction</h1><p>Les vampires perdent du liquide vital chaque nuit. Le grimoire contient les règles de la malédiction BloodMoon.</p>'
                '</main></body></html>')
        title, text, links = kb.parse_page(html)
        self.assertIn("/roleplay/pages/guide.php?lang=fr", links)
        self.assertEqual(title, "BloodMoon RP")
        self.assertNotIn("SECRET", text)
        self.assertNotIn("Administration privee", text)
        with tempfile.TemporaryDirectory() as directory:
            db = kb.connect(Path(directory) / "knowledge.db")
            try:
                state, count = kb.store(db, "roleplay", kb.SOURCES["roleplay"], title, text)
                self.assertEqual(state, "indexed")
                self.assertGreater(count, 0)
                hits = kb.safe_search(db, "vampires malediction")
                self.assertEqual(hits[0]["source"], "roleplay")
                self.assertEqual(hits[0]["url"], "https://bloodmoonpack.com/")
                self.assertEqual(kb.store(db, "roleplay", kb.SOURCES["roleplay"], title, text)[0], "unchanged")
                self.assertEqual(kb.safe_search(db, '"; DROP TABLE documents; --'), [])
                self.assertEqual(db.execute("SELECT count(*) FROM knowledge_pages").fetchone()[0], 1)
            finally:
                db.close()

    def test_menu_link_scope(self):
        self.assertEqual(kb.approved("grid", "https://bloodmoonpack.com/grid/viewer.php"), "https://bloodmoonpack.com/grid/viewer.php")
        self.assertEqual(kb.approved("roleplay", "https://bloodmoonpack.com/roleplay/pages/guide.php?lang=fr"), "https://bloodmoonpack.com/roleplay/pages/guide.php?lang=fr")
        self.assertIsNone(kb.approved("grid", "https://bloodmoonpack.com/grid/login.php"))
        self.assertIsNone(kb.approved("roleplay", "https://bloodmoonpack.com/grid/"))
        pdf_url = "https://bloodmoonpack.com/Download/GUIDE/THE_CURSE_GB.pdf"
        self.assertEqual(kb.approved("roleplay", pdf_url), pdf_url)
        self.assertIsNone(kb.approved("grid", pdf_url))
        self.assertIsNone(kb.approved("roleplay", "https://bloodmoonpack.com/Download/PRIVATE/secret.pdf"))
        self.assertIsNone(kb.approved("roleplay", "https://other.invalid/Download/GUIDE/guide.pdf"))
        self.assertEqual(kb.MAX_SITE_PAGES, 2500)
        guide_html = '<nav><a href="/roleplay/pages/guide.php">Guide</a></nav><a href="/Download/GUIDE/THE_CURSE_GB.pdf">PDF</a>'
        _, _, links = kb.parse_page(guide_html)
        self.assertIn("/Download/GUIDE/THE_CURSE_GB.pdf", links)

    def test_pdfinfo_page_count_regex_and_extraction(self):
        # Regression: the previous double-escaped regex rejected EVERY guide PDF.
        calls = []
        def fake_run(argv, **kwargs):
            calls.append(argv[0])
            if "pdfinfo" in argv[0]:
                return SimpleNamespace(returncode=0, stdout="Title: Guide\\nPages:          3\\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="Règles du jeu BloodMoon " * 10, stderr="")
        with patch.object(kb.subprocess, "run", side_effect=fake_run):
            content = kb.extract_pdf(b"%PDF-1.7\\nexample")
        self.assertIn("Règles du jeu", content)
        self.assertEqual(calls, ["/usr/bin/pdfinfo", "/usr/bin/pdftotext"])

    def test_known_private_urls_excluded(self):
        for source, url in (
            ("grid", "https://bloodmoonpack.com/grid/events/add.php"),
            ("grid", "https://bloodmoonpack.com/grid/events/my-events.php"),
            ("grid", "https://bloodmoonpack.com/grid/join.php"),
            ("marketplace", "https://bloodmoonpack.com/Marketplace/favorites.php?lang=fr"),
            ("marketplace", "https://bloodmoonpack.com/Marketplace/seller.php?lang=en"),
        ):
            self.assertIsNone(kb.approved(source, url))
        self.assertEqual(kb.MAX_RESPONSE_BYTES, 8_000_000)

    def test_invalid_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            db = kb.connect(Path(directory) / "knowledge.db")
            try:
                with self.assertRaises(ValueError):
                    kb.store(db, "admin", "https://bloodmoonpack.com/admin/", "bad", "do not index")
                self.assertFalse(kb.safe_search(db, ""))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
