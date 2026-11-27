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
    def test_sort_and_paginate_all_records_before_slicing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "catalog" / "catalog.json"
            path.parent.mkdir()
            records = [
                {"provider": "groq", "providerName": "Groq", "model": f"model-{i:03d}",
                 "modelName": f"Model {i:03d}", "sourceUrl": "https://free-llm.com/provider/groq",
                 "freeTierClaim": "unknown", "routerCompatible": True,
                 "contextTokens": i * 100, "vision": False}
                for i in range(75)
            ]
            path.write_text(json.dumps({
                "schemaVersion": 2, "generatedAtUtc": "2026-11-27T12:00:00Z",
                "source": "https://free-llm.com", "models": records,
            }))
            with patch.object(control, "FLEET_ROOT", root):
                first = control.catalog_list({"sort": "model", "direction": "desc", "page": 1})
                last = control.catalog_list({"sort": "model", "direction": "desc", "page": 3})
                self.assertEqual(first["total"], 75)
                self.assertEqual(first["pages"], 3)
                self.assertEqual(len(first["models"]), 25)
                self.assertEqual(first["models"][0]["model"], "model-074")
                self.assertEqual(last["models"][0]["model"], "model-024")
                seen = [
                    item["model"]
                    for page in range(1, 4)
                    for item in control.catalog_list({
                        "sort": "model", "direction": "desc", "page": page
                    })["models"]
                ]
                self.assertEqual(len(seen), 75)
                self.assertEqual(len(set(seen)), 75)
                self.assertEqual(control.catalog_list({"page": 900})["page"], 3)
                self.assertEqual(control.catalog_list({"sort": "context", "direction": "asc"})["models"][0]["contextTokens"], 0)
                for invalid in ({"sort": "apiKey"}, {"direction": "sideways"},
                                {"page": -1}, {"page": "2"}):
                    with self.assertRaises(control.ControlError):
                        control.catalog_list(invalid)

    def test_catalog_lookup_is_read_only_and_rejects_unknown_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "catalog" / "catalog.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "schemaVersion": 2, "generatedAtUtc": "2026-11-27T12:00:00Z",
                "models": [
                    {"provider": "groq", "model": "openai/gpt-oss-20b",
                     "modelName": "GPT OSS 20B", "routerCompatible": True},
                    {"provider": "groq", "model": "made-up-model",
                     "modelName": "Other", "routerCompatible": True},
                    {"provider": "unknown", "model": "other", "modelName": "Other"}
                ]
            }))
            unchanged = path.read_bytes()
            with patch.object(control, "FLEET_ROOT", root):
                candidate = control.catalog_lookup({
                    "provider": "groq", "model": "openai/gpt-oss-20b"})
                self.assertEqual(candidate["provider"], "Groq")
                self.assertEqual(candidate["enabled"], False)
                self.assertEqual(candidate["configured"], False)
                self.assertTrue(candidate["publicEligible"])
                for bad in (
                    {"provider": "evil", "model": "anything"},
                    {"provider": "groq", "model": "not-in-catalog"},
                    {"provider": "groq", "model": "../../etc/passwd"},
                    {"provider": "unknown", "model": "other"},
                    {"provider": "groq"},
                ):
                    with self.assertRaises(control.ControlError):
                        control.catalog_lookup(bad)
            self.assertEqual(path.read_bytes(), unchanged)

    def test_groq_cloud_is_found_as_groq_and_can_be_prepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "catalog" / "catalog.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "schemaVersion": 2, "generatedAtUtc": "2026-11-27T12:00:00Z",
                "models": [{
                    "provider": "groq-cloud", "providerName": "Groq",
                    "model": "openai/gpt-oss-120b", "modelName": "GPT OSS 120B",
                    "routerCompatible": False, "sourceUrl": "https://free-llm.com/provider/groq-cloud"
                }]
            }))
            with patch.object(control, "FLEET_ROOT", root):
                matches = control.catalog_list({"provider": "groq", "compatibility": "supported"})
                self.assertEqual(matches["total"], 1)
                self.assertTrue(matches["models"][0]["routerCompatible"])
                prepared = control.catalog_lookup({
                    "provider": "groq-cloud", "model": "openai/gpt-oss-120b"})
                self.assertEqual(prepared["provider"], "Groq")
                self.assertFalse(prepared["enabled"])

    def test_all_supported_providers_use_catalog_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "catalog" / "catalog.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "schemaVersion": 2, "generatedAtUtc": "2026-11-27T12:00:00Z",
                "models": [
                    {"provider": "groq-cloud", "providerName": "Groq",
                     "model": "openai/gpt-oss-20b", "modelName": "GPT OSS 20B",
                     "routerCompatible": False},
                    {"provider": "google-ai-studio", "providerName": "Google AI Studio",
                     "model": "gemini-3.5-flash-lite", "modelName": "Gemini 3.5 Flash Lite",
                     "routerCompatible": False},
                    {"provider": "openrouter", "providerName": "OpenRouter",
                     "model": "google/gemma-4-31b-it:free", "modelName": "Gemma",
                     "routerCompatible": True},
                    {"provider": "vertex-ai-express", "providerName": "Google Vertex AI",
                     "model": "gemini-2.5-flash", "modelName": "Gemini 2.5 Flash",
                     "routerCompatible": False}
                ]
            }))
            with patch.object(control, "FLEET_ROOT", root):
                for alias, expected_slug, expected_adapter, model in [
                    ("Groq", "groq-cloud", "Groq", "openai/gpt-oss-20b"),
                    ("Gemini", "google-ai-studio", "Gemini", "gemini-3.5-flash-lite"),
                    ("Google AI Studio", "google-ai-studio", "Gemini", "gemini-3.5-flash-lite"),
                    ("OpenRouter", "openrouter", "OpenRouter", "google/gemma-4-31b-it:free")
                ]:
                    matches = control.catalog_list({"provider": alias, "compatibility": "supported"})
                    self.assertEqual(matches["total"], 1, alias)
                    self.assertEqual(matches["models"][0]["provider"], expected_slug)
                    selection = control.catalog_lookup({"provider": expected_slug, "model": model})
                    self.assertEqual(selection["provider"], expected_adapter)
                    self.assertFalse(selection["enabled"])
                gemini = control.catalog_list({"query": "Gemini", "compatibility": "supported"})
                self.assertEqual(gemini["total"], 1)
                self.assertEqual(gemini["models"][0]["provider"], "google-ai-studio")
                other = control.catalog_list({"provider": "vertex", "compatibility": "other"})
                self.assertEqual(other["total"], 1)
                with self.assertRaises(control.ControlError):
                    control.catalog_lookup({"provider": "vertex-ai-express", "model": "gemini-2.5-flash"})

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
