"""Public packaging and configuration sanity checks for the repository.

These tests protect the release surface from drift without requiring a grid,
a remote API key, or a live BloodMoon installation.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepositoryConsistencyTests(unittest.TestCase):
    def test_safe_example_configurations_match_runtime_options(self):
        allowed = {"Grid", "Bot", "Ai"}
        for filename in ("config/appsettings.example.json", "config/bloodmoon.example.json"):
            with self.subTest(filename=filename):
                config = json.loads((ROOT / filename).read_text(encoding="utf-8"))
                self.assertEqual(set(config), allowed)
                self.assertFalse(config["Ai"]["Enabled"])
                self.assertFalse(config["Ai"]["PublicAccess"])
                self.assertEqual(config["Ai"]["AuthorizedUuidList"], [])
                self.assertEqual(config["Grid"]["AvatarPasswordEnv"], "OSAI_AVATAR_PASSWORD")
                self.assertNotIn("AvatarPassword", config["Grid"])
                self.assertTrue(config["Grid"]["LoginUri"])
                self.assertIn(config["Grid"]["StartLocation"]["Mode"], ("Region", "Last"))

    def test_readme_local_links_are_present(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", readme):
            if target.startswith(("https://", "http://", "#")):
                continue
            with self.subTest(target=target):
                self.assertTrue((ROOT / target.split("#", 1)[0]).is_file())

    def test_expected_components_are_packaged(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        for path in (
            "controller/protected_terms.py", "web/OpenSim_AI/index.php",
            "deploy/php/ai-translate.php",
        ):
            with self.subTest(path=path):
                self.assertIn(path, workflow)
                self.assertTrue((ROOT / path).is_file())

    def test_private_runtime_files_are_gitignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        for protected in ("ai-api-key.txt", "ai-keys/", "config/multi-ai.json",
                          "config/translation.json", "config/knowledge-terms.json",
                          "web-admin.php", "bot-password.txt"):
            with self.subTest(file=protected):
                self.assertIn(protected, ignore)

    def test_no_real_secrets_in_example_config(self):
        for name in ("config/appsettings.example.json", "config/bloodmoon.example.json"):
            config = json.loads((ROOT / name).read_text(encoding="utf-8"))
            # ApiKeyEnv names an environment variable, not a credential.
            # Check for unexpected fields containing secret material instead.
            allowed_ai = {"Enabled", "Provider", "Model", "ApiKeyEnv",
                          "AuthorizedUuidList", "PublicAccess",
                          "MaxRequestsPerHour", "MinSecondsBetweenRequests", "SystemPrompt"}
            self.assertEqual(set(config["Ai"]), allowed_ai)
            self.assertTrue(config["Ai"]["ApiKeyEnv"].startswith("OSAI_"))
            self.assertNotIn("apiKey", config["Ai"])
            self.assertNotIn("AvatarPassword", config["Grid"])


if __name__ == "__main__":
    unittest.main()
