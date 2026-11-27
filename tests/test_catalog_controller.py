"""No secret-bearing catalog fields may cross the controller socket."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import control
import catalog_cache


class CatalogControllerTests(unittest.TestCase):
    def test_read_only_filtered_catalog_and_missing_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(control, "FLEET_ROOT", root):
                self.assertFalse(control.catalog_list()["available"])
                path = root / "catalog" / "catalog.json"
                path.parent.mkdir()
                source = json.dumps({
                    "schema_version": 2, "source": "https://free-llm.com",
                    "generated_at": "2026-11-27T01:04:35+01:00",
                    "providers": [
                        {"slug": "groq", "name": "Groq", "type": "API",
                         "url": "https://free-llm.com/provider/groq",
                         "base_url": "https://api.groq.com/openai/v1",
                         "free_tier": "truly_free",
                         "models": [{"id": "openai/gpt-oss-20b",
                                     "name": "GPT OSS 20B", "kind": "chat"}]},
                        {"slug": "other", "name": "Other", "type": "API",
                         "url": "https://free-llm.com/provider/other",
                         "base_url": "https://api.example.org/v1",
                         "models": [{"id": "something", "name": "Other AI", "kind": "chat"}]}
                    ]
                }).encode()
                catalog_cache.refresh(path, lambda: source)
                results = control.catalog_list({"query": "gpt", "compatibility": "supported"})
                self.assertEqual(results["total"], 1)
                self.assertEqual(results["models"][0]["provider"], "groq")
                self.assertNotIn("approved", results["models"][0])
                self.assertNotIn("apiBaseUrl", results["models"][0])
                results = control.catalog_list({"compatibility": "other"})
                self.assertEqual(results["total"], 1)
                self.assertEqual(results["models"][0]["model"], "something")
                with self.assertRaises(control.ControlError):
                    control.catalog_list({"unsupportedFlag": True})
                with self.assertRaises(control.ControlError):
                    control.catalog_list({"query": "x" * 101})


if __name__ == "__main__":
    unittest.main()
