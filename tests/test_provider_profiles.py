import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import provider_profiles


class MultiProviderConfigurationTests(unittest.TestCase):
    def settings(self):
        return {
            "enabled": True, "mode": "single",
            "profiles": [
                {"id": "primary", "provider": "Groq", "model": "openai/gpt-oss-20b",
                 "enabled": True, "verified": True, "apiKey": ""}
            ],
            "maxRequestsPerHour": 30, "minSecondsBetweenRequests": 15,
            "systemPrompt": "Tu es BloodMoon AI."
        }

    def test_legacy_groq_preserved(self):
        c = provider_profiles.normalize(self.settings())
        self.assertEqual(c["Mode"], "single")
        self.assertEqual(c["Profiles"][0]["ApiKeyEnv"], "OSAI_GROQ_API_KEY")

    def test_auto_with_two_free_providers(self):
        c = self.settings()
        c["mode"] = "auto"
        c["profiles"].append(
            {"id": "router", "provider": "OpenRouter", "model": "openrouter/free",
             "enabled": True, "verified": True, "apiKey": ""}
        )
        self.assertEqual(len(provider_profiles.normalize(c)["Profiles"]), 2)

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
