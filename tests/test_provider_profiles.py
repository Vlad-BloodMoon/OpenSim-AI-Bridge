import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import provider_profiles


class MultiProviderConfigurationTests(unittest.TestCase):
    def settings(self):
        return {
            "enabled": True, "mode": "auto",
            "profiles": [
                {"id": "primary", "provider": "Groq", "model": "openai/gpt-oss-20b",
                 "enabled": True, "verified": True, "apiKey": ""}
            ],
            "maxRequestsPerHour": 30, "minSecondsBetweenRequests": 15,
            "systemPrompt": "Tu es BloodMoon AI."
        }

    def test_legacy_groq_preserved(self):
        c = provider_profiles.normalize(self.settings())
        self.assertEqual(c["Mode"], "auto")
        self.assertEqual(c["Profiles"][0]["ApiKeyEnv"], "OSAI_GROQ_API_KEY")

    def test_auto_with_two_free_providers(self):
        c = self.settings()
        c["mode"] = "auto"
        c["profiles"].append(
            {"id": "router", "provider": "OpenRouter", "model": "openrouter/free",
             "enabled": True, "verified": True, "apiKey": ""}
        )
        self.assertEqual(len(provider_profiles.normalize(c)["Profiles"]), 2)

    def test_auto_three_independent_free_providers(self):
        c = self.settings()
        c["profiles"] += [
            {"id": "router", "provider": "OpenRouter", "model": "openrouter/free",
             "enabled": True, "verified": True, "apiKey": ""},
            {"id": "gemini", "provider": "Gemini", "model": "gemini-3-flash-preview",
             "enabled": True, "verified": True, "apiKey": ""},
        ]
        profiles = provider_profiles.normalize(c)["Profiles"]
        self.assertEqual([p["Provider"] for p in profiles],
                         ["Groq", "OpenRouter", "Gemini"])
        self.assertEqual(profiles[2]["ApiKeyEnv"], "OSAI_GEMINI_API_KEY")
        self.assertEqual(provider_profiles.provider_key_path("/tmp", "Gemini"),
                         Path("/tmp/ai-keys/gemini.txt"))

    def test_several_models_of_one_provider_share_single_key(self):
        c = self.settings()
        for i, name in enumerate(("gemini-3-flash-preview", "gemini-3.5-flash-lite",
                                  "gemini-3.1-flash-lite")):
            c["profiles"].append({
                "id": f"gemini-{i}", "provider": "Gemini", "model": name,
                "enabled": True, "verified": True, "apiKey": ""
            })
        models = provider_profiles.normalize(c)["Profiles"]
        self.assertEqual(len(models), 4)
        self.assertEqual(len(set(m["ApiKeyEnv"] for m in models[1:])), 1)
        self.assertEqual(models[1]["ApiKeyEnv"], "OSAI_GEMINI_API_KEY")

    def test_sixteen_model_profiles_supported(self):
        c = self.settings()
        for i in range(15):
            c["profiles"].append({
                "id": f"groq-{i}", "provider": "Groq",
                "model": "openai/gpt-oss-20b", "enabled": False,
                "verified": False, "apiKey": ""
            })
        self.assertEqual(len(provider_profiles.normalize(c)["Profiles"]), 16)
        c["profiles"].append(c["profiles"][-1].copy())
        c["profiles"][-1]["id"] = "groq-overflow"
        with self.assertRaises(provider_profiles.ProfileError):
            provider_profiles.normalize(c)

    def test_gemini_non_free_models_rejected(self):
        c = self.settings()
        c["profiles"][0]["provider"] = "Gemini"
        c["profiles"][0]["model"] = "gemini-2.5-pro"
        with self.assertRaises(provider_profiles.ProfileError):
            provider_profiles.normalize(c)

    def test_reject_paid_public_provider(self):
        for name, model in (("OpenAI", "gpt-4.1-mini"),
                            ("OpenRouter", "openai/gpt-4o-mini")):
            with self.subTest(name=name):
                c = self.settings()
                c["profiles"][0]["provider"] = name
                c["profiles"][0]["model"] = model
                with self.assertRaises(provider_profiles.ProfileError):
                    provider_profiles.normalize(c)

    def test_reject_duplicate_profile_and_untrusted_extra_fields(self):
        c = self.settings()
        c["profiles"].append(c["profiles"][0].copy())
        with self.assertRaises(provider_profiles.ProfileError):
            provider_profiles.normalize(c)
        c = self.settings()
        c["profiles"][0]["keyPath"] = "/etc/shadow"
        with self.assertRaises(provider_profiles.ProfileError):
            provider_profiles.normalize(c)

    def test_reject_unverified_only_configuration(self):
        c = self.settings()
        c["profiles"][0]["verified"] = False
        with self.assertRaises(provider_profiles.ProfileError):
            provider_profiles.normalize(c)

    def test_key_destination_is_fixed(self):
        with self.assertRaises(provider_profiles.ProfileError):
            provider_profiles.provider_key_path("/tmp", "../../root")


if __name__ == "__main__":
    unittest.main()
