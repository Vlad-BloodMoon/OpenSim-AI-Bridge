"""Offline regression tests: no network access, no grid service required."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "knowledge" / "knowledge_cli.py"
spec = importlib.util.spec_from_file_location("bloodmoon_knowledge_cli", MODULE)
kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb)


class KnowledgeTests(unittest.TestCase):
    def test_parse_and_search(self):
        html = ('<html><head><title>BloodMoon RP</title><script>SECRET</script></head>'
                '<body><nav>Administration privee</nav><main>'
                '<h1>Vampires et malediction</h1><p>Les vampires perdent du liquide vital.</p>'
                '</main></body></html>')
        title, text = kb.parse_page(html)
        self.assertEqual(title, "BloodMoon RP")
        self.assertNotIn("SECRET", text)
        self.assertNotIn("Administration privee", text)
        with tempfile.TemporaryDirectory() as directory:
            db = kb.connect(Path(directory) / "knowledge.db")
            try:
                state, count = kb.store(db, "roleplay", title, text)
                self.assertEqual(state, "indexed")
                self.assertGreater(count, 0)
                hits = kb.safe_search(db, "vampires malediction")
                self.assertEqual(hits[0]["source"], "roleplay")
                self.assertEqual(hits[0]["url"], "https://bloodmoonpack.com/")
                self.assertEqual(kb.store(db, "roleplay", title, text)[0], "unchanged")
                self.assertEqual(kb.safe_search(db, '"; DROP TABLE documents; --'), [])
                self.assertEqual(db.execute("SELECT count(*) FROM documents").fetchone()[0], 1)
            finally:
                db.close()

    def test_invalid_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            db = kb.connect(Path(directory) / "knowledge.db")
            try:
                with self.assertRaises(ValueError):
                    kb.store(db, "admin", "bad", "do not index")
                self.assertFalse(kb.safe_search(db, ""))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
