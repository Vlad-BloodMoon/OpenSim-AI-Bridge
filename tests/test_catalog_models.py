"""V2 catalog normalization must never activate a provider or leak fields."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
from catalog_models import CatalogError, normalize_catalog


def sample():
    return {
        "schema_version": 2,
        "source": "https://free-llm.com",
        "generated_at": "2026-11-27T01:04:35+01:00",
        "providers": [
            {"slug": "groq", "name": "Groq", "type": "API",
             "url": "https://free-llm.com/provider/groq",
             "base_url": "https://api.groq.com/openai/v1",
             "free_tier": "truly_free", "rate_limit": "<script>x</script>",
             "models": [{"id": "openai/gpt-oss-20b", "name": "GPT OSS 20b",
                         "kind": "chat", "context_tokens": 131072},
                        {"id": "openai/gpt-oss-20b", "name": "Duplicate", "kind": "chat"},
                        {"id": "visual", "name": "Image", "kind": "image"}]},
            {"slug": "local-model", "name": "Ollama", "type": "Local",
             "url": "https://free-llm.com/provider/ollama",
             "base_url": "http://localhost:11434",
             "models": [{"id": "qwen", "name": "Local", "kind": "chat"}]},
            {"slug": "unknown-provider", "name": "Hosted service", "type": "Proxy",
             "url": "https://free-llm.com/provider/unknown-provider",
             "base_url": "https://api.example.com/v1",
             "models": [{"id": "some-model", "name": "Another AI", "kind": "chat"}]}
        ]
    }


class CatalogTests(unittest.TestCase):
    def test_only_remote_chat_models_and_no_approval(self):
        catalog = normalize_catalog(sample())
        self.assertEqual(len(catalog["models"]), 2)
        self.assertEqual([e["model"] for e in catalog["models"]],
                         ["openai/gpt-oss-20b", "some-model"])
        self.assertTrue(catalog["models"][0]["routerCompatible"])
        self.assertFalse(catalog["models"][1]["routerCompatible"])
        for entry in catalog["models"]:
            self.assertIs(entry["approved"], False)
            self.assertIs(entry["enabled"], False)
            self.assertIs(entry["costVerified"], False)

    def test_explicit_remote_provider_aliases_only(self):
        from catalog_models import adapter_for_slug, catalog_provider_search_text
        self.assertEqual(adapter_for_slug("groq-cloud"), "Groq")
        self.assertEqual(adapter_for_slug("google-ai-studio"), "Gemini")
        self.assertEqual(adapter_for_slug("openrouter"), "OpenRouter")
        self.assertIsNone(adapter_for_slug("vertex-ai-express"))
        self.assertIsNone(adapter_for_slug("random-google-proxy"))
        self.assertIn("Gemini", catalog_provider_search_text("google-ai-studio", "Google AI Studio"))
        payload = sample()
        payload["providers"][0]["slug"] = "google-ai-studio"
        payload["providers"][0]["name"] = "Google AI Studio"
        payload["providers"][0]["url"] = "https://free-llm.com/provider/google-ai-studio"
        normalized = normalize_catalog(payload)
        self.assertTrue(normalized["models"][0]["routerCompatible"])
        self.assertFalse(normalized["models"][0]["enabled"])

    def test_malicious_and_invalid_metadata(self):
        payload = sample()
        payload["providers"][0]["url"] = "https://attacker@free-llm.com/provider/groq"
        catalog = normalize_catalog(payload)
        self.assertEqual(len(catalog["models"]), 1)
        payload = sample()
        payload["providers"][0]["models"].append({
            "id": "<script>alert(1)</script>", "name": "<b>evil</b>", "kind": "chat"})
        self.assertEqual(len(normalize_catalog(payload)["models"]), 2)

    def test_reject_untrusted_source_and_schema(self):
        payload = sample()
        payload["source"] = "https://evil.example"
        with self.assertRaises(CatalogError):
            normalize_catalog(payload)
        payload = sample()
        payload["schema_version"] = 3
        with self.assertRaises(CatalogError):
            normalize_catalog(payload)
        payload = sample()
        payload["generated_at"] = "sometime"
        with self.assertRaises(CatalogError):
            normalize_catalog(payload)

    def test_absence_is_not_a_router_dependency(self):
        self.assertEqual(normalize_catalog({
            "schema_version": 2,
            "source": "https://free-llm.com",
            "generated_at": "2026-11-27T01:04:35Z",
            "providers": [],
        })["models"], [])


if __name__ == "__main__":
    unittest.main()
