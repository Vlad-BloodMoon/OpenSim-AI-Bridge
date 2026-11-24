"""Vocabulary admin CRUD tests; never use production bot files."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import protected_terms


class ProtectedTermsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        (self.base / "config").mkdir()
        (self.base / "appsettings.json").write_text("{}", encoding="utf-8")

    def test_defaults_then_modify_add_delete_and_read(self):
        initial = protected_terms.read(self.base)
        self.assertGreater(len(initial), 5)
        self.assertEqual(initial[0]["term"], "Grid")
        result = protected_terms.upsert(self.base, {
            "previous": "Grid", "term": "Grid",
            "aliases": "grille, grade", "keywords": "grid, grille, service",
            "domain": "grid",
        })
        self.assertTrue(result["saved"])
        protected_terms.upsert(self.base, {
            "previous": "", "term": "Soul Reaper",
            "aliases": "Faucheur d'âmes", "keywords": "âme, soul, reaper",
            "domain": "roleplay",
        })
        self.assertEqual(protected_terms.read(self.base)[-1]["term"], "Soul Reaper")
        self.assertEqual(protected_terms.read(self.base)[0]["aliases"], "grille, grade")
        self.assertEqual(protected_terms.config_path(self.base).stat().st_mode & 0o777, 0o600)
        protected_terms.delete(self.base, {"term": "Soul Reaper"})
        self.assertFalse(any(e["term"] == "Soul Reaper" for e in protected_terms.read(self.base)))

    def test_reject_invalid_and_duplicate_values(self):
        cases = [
            {"previous": "", "term": "Grid", "aliases": "", "keywords": "abc", "domain": "grid"},
            {"previous": "", "term": "<script>", "aliases": "", "keywords": "abc", "domain": "grid"},
            {"previous": "", "term": "abcdef", "aliases": "", "keywords": "", "domain": "grid"},
            {"previous": "", "term": "abcdef", "aliases": "", "keywords": "abc", "domain": "invalid"},
            {"previous": "", "term": "abcdef", "aliases": "a" * 1000, "keywords": "abc", "domain": "grid"},
            {"previous": "nonexistent", "term": "abcdef", "aliases": "", "keywords": "abc", "domain": "grid"},
        ]
        for item in cases:
            with self.subTest(item=item["term"], aliases=item["aliases"][:10]):
                with self.assertRaises(protected_terms.TermsError):
                    protected_terms.upsert(self.base, item)
        self.assertFalse(protected_terms.config_path(self.base).exists())

    def test_edit_removal_and_empty_list(self):
        for initial in list(protected_terms.read(self.base)):
            protected_terms.delete(self.base, {"term": initial["term"]})
        self.assertEqual(protected_terms.read(self.base), [])


if __name__ == "__main__":
    unittest.main()
