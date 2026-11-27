"""Offline checks: successful cache refresh and fail-safe last-good fallback."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import catalog_cache
from catalog_models import CatalogError


class CatalogCacheTests(unittest.TestCase):
    def source(self):
        return json.dumps({
            "schema_version": 2, "source": "https://free-llm.com",
            "generated_at": "2026-11-27T01:04:35+01:00",
            "providers": [{
                "type": "API", "slug": "groq", "name": "Groq",
                "url": "https://free-llm.com/provider/groq",
                "base_url": "https://api.groq.com/openai/v1",
                "models": [{"kind": "chat", "id": "openai/gpt-oss-20b",
                            "name": "GPT OSS 20B"}]
            }]
        }).encode("utf-8")

    def test_last_good_cache_survives_invalid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "catalog.json"
            result = catalog_cache.refresh(path, self.source)
            self.assertEqual(result["models"], 1)
            original = path.read_bytes()
            self.assertFalse(catalog_cache.read_cache(path)["models"][0]["enabled"])
            with self.assertRaises(CatalogError):
                catalog_cache.refresh(path, lambda: b"{not json")
            self.assertEqual(path.read_bytes(), original)
            with self.assertRaises(CatalogError):
                catalog_cache.refresh(path, lambda: b"x" * (catalog_cache.MAX_DOWNLOAD_BYTES + 1))
            self.assertEqual(path.read_bytes(), original)

    def test_missing_or_symlink_cache_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "catalog.json"
            self.assertIsNone(catalog_cache.read_cache(cache))
            target = root / "target.json"
            target.write_text("private")
            cache.symlink_to(target)
            with self.assertRaises(CatalogError):
                catalog_cache.refresh(cache, self.source)
            self.assertEqual(target.read_text(), "private")


if __name__ == "__main__":
    unittest.main()
