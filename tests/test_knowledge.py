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
                return SimpleNamespace(returncode=0, stdout="Title: Guide\nPages:          3\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="Règles du jeu BloodMoon " * 10, stderr="")
        with patch.object(kb.subprocess, "run", side_effect=fake_run):
            content = kb.extract_pdf(b"%PDF-1.7\nexample")
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

    def test_curated_local_notes_index_update_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "AI_Knowledge"
            for category in kb.LOCAL_CATEGORIES:
                (root / category).mkdir(parents=True)
            note = root / "grid_bloodmoon" / "terrains-freelands.txt"
            note.write_text(
                "Pour avoir un terrain sur BloodMoon Grid, cherchez les Freelands. "
                "Ce sont des terrains proposés directement par la grille. "
                "Pour connaître les disponibilités, demandez aux responsables.",
                encoding="utf-8")
            db = kb.connect(Path(directory) / "kb.db")
            try:
                stats = kb.import_local(db, root)
                self.assertEqual(stats["indexed"], 1)
                hits = kb.safe_search(db, "terrain freelands")
                self.assertTrue(any(h["source"] == "local_grid_bloodmoon" for h in hits))
                self.assertEqual(kb.import_local(db, root)["unchanged"], 1)
                note.write_text(
                    "Les freelands sont des terrains proposés par BloodMoon Grid. "
                    "Consultez la grille pour connaître les disponibilités et conditions.",
                    encoding="utf-8")
                self.assertEqual(kb.import_local(db, root)["indexed"], 1)
                note.unlink()
                self.assertEqual(kb.import_local(db, root)["deleted"], 1)
                self.assertFalse(kb.safe_search(db, "freelands"))
            finally:
                db.close()

    def test_reject_symlink_and_unapproved_local_url(self):
        self.assertEqual(
            kb.approved("local_grid_bloodmoon", "knowledge://grid_bloodmoon/terrains.txt"),
            "knowledge://grid_bloodmoon/terrains.txt")
        self.assertIsNone(kb.approved("local_grid_bloodmoon", "knowledge://grid_bloodmoon/../secret.txt"))
        self.assertIsNone(kb.approved("local_grid_bloodmoon", "https://other.invalid/terrains.txt"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "notes"
            for category in kb.LOCAL_CATEGORIES:
                (root / category).mkdir(parents=True)
            (root / "grid_bloodmoon" / "private.txt").symlink_to(Path(directory) / "secret")
            db = kb.connect(Path(directory) / "kb.db")
            try:
                with self.assertRaises(ValueError):
                    kb.import_local(db, root)
            finally:
                db.close()

    def test_recursive_files_pdfs_incremental_complete_and_pruning(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "files"
            physics = root / "Physics_Engine"
            biography = root / "Divers" / "Bio"
            physics.mkdir(parents=True)
            biography.mkdir(parents=True)
            first = physics / "uBODE test.pdf"
            second = biography / "Vlad_FR.pdf"
            first.write_bytes(b"%PDF-1.4 first")
            second.write_bytes(b"%PDF-1.4 second")
            db = kb.connect(Path(directory) / "knowledge.db")
            def fake_pdf(argv, **kwargs):
                self.assertEqual(argv[0], "/usr/bin/pdftotext")
                changed = b"updated" in Path(argv[-2]).read_bytes()
                return SimpleNamespace(
                    returncode=0,
                    stdout=(b"uBODE documentation for OpenSimulator " * 5
                            + b"\x0c"
                            + b"Second page of physics and movement explanation " * 5
                            + (b" Updated document text." if changed else b"")
                            + b"\x0c"))
            try:
                with patch.object(kb.subprocess, "run", side_effect=fake_pdf) as runner:
                    result = kb.import_files_pdfs(db, root)
                    self.assertEqual((result["indexed"], result["errors"]), (2, 0))
                    self.assertEqual(result["pages"], 4)
                    self.assertEqual(runner.call_count, 2)
                    rows = db.execute("SELECT source,url FROM knowledge_pages ORDER BY url").fetchall()
                    self.assertEqual([s for s, _ in rows], ["grid", "handbook"])
                    self.assertTrue(all(u.startswith(kb.FILES_PDF_PREFIX) for _, u in rows))
                    self.assertTrue(kb.safe_search(db, "Second page of physics"))
                    result = kb.import_files_pdfs(db, root)
                    self.assertEqual(result["unchanged"], 2)
                    self.assertEqual(runner.call_count, 2)
                    first.write_bytes(b"%PDF-1.4 updated")
                    result = kb.import_files_pdfs(db, root)
                    self.assertEqual(result["indexed"], 1)
                    self.assertEqual(result["unchanged"], 1)
                    second.unlink()
                    result = kb.import_files_pdfs(db, root)
                    self.assertEqual(result["deleted"], 1)
                    self.assertEqual(db.execute("SELECT count(*) FROM knowledge_pages").fetchone()[0], 1)
            finally:
                db.close()

    def test_files_pdfs_reject_unapproved_paths_and_symlink(self):
        from unittest.mock import patch
        self.assertIsNone(kb.approved("handbook",
            "https://bloodmoonpack.com/files/%2E%2E/password.pdf"))
        self.assertIsNone(kb.approved("grid",
            "https://bloodmoonpack.com/files/../../../admin.pdf"))
        self.assertIsNone(kb.approved("roleplay",
            "https://bloodmoonpack.com/files/PDF.pdf"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "files"
            root.mkdir()
            (root / "not-real.pdf").symlink_to(Path(directory) / "outside.pdf")
            db = kb.connect(Path(directory) / "knowledge.db")
            try:
                with patch.object(kb.subprocess, "run") as runner:
                    stats = kb.import_files_pdfs(db, root)
                    self.assertEqual(stats["files"], 0)
                    runner.assert_not_called()
            finally:
                db.close()

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
