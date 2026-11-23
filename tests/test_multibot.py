import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import multi_bot


class BotValidationTests(unittest.TestCase):
    def valid(self):
        return {"firstName": "Test", "lastName": "Resident", "password": "example-private-secret",
                "region": "BloodMoon_TEST", "x": 128, "y": 128, "z": 25}

    def test_valid(self):
        self.assertEqual(multi_bot.validate_create(self.valid())["region"], "BloodMoon_TEST")

    def test_varregion_coordinates_above_256_are_allowed(self):
        c = self.valid()
        c["x"], c["y"], c["z"] = 347, 320, 124
        result = multi_bot.validate_create(c)
        self.assertEqual((result["x"], result["y"], result["z"]), (347, 320, 124))

    def test_no_unit_injection(self):
        for bad in ("../../root", "main", "test;shutdown", "A" * 16, "", "deadbeef"):
            with self.subTest(bad=bad):
                with self.assertRaises(multi_bot.BotRegistryError):
                    multi_bot.bot_unit(bad)

    def test_password_is_not_multiline(self):
        for secret in ("test\nextra", "test\r", ""):
            with self.subTest(secret=secret):
                c = self.valid()
                c["password"] = secret
                with self.assertRaises(multi_bot.BotRegistryError):
                    multi_bot.validate_create(c)

    def test_valid_coordinates_only(self):
        for field, value in (("x", -1), ("y", 8193), ("z", 4097), ("x", True), ("y", 5.2)):
            with self.subTest(field=field, value=value):
                c = self.valid()
                c[field] = value
                with self.assertRaises(multi_bot.BotRegistryError):
                    multi_bot.validate_create(c)

    def test_reject_extra_fields(self):
        c = self.valid()
        c["Unit"] = "ssh.service"
        with self.assertRaises(multi_bot.BotRegistryError):
            multi_bot.validate_create(c)

    def test_main_avatar_cannot_be_deleted(self):
        with self.assertRaises(multi_bot.BotRegistryError):
            multi_bot.delete_bot("main", "BloodMoon AI")

    @patch.object(multi_bot, "bot_path")
    def test_name_must_match_before_service_is_touched(self, mock_path):
        mock_path.return_value = Path("/tmp/test-delete-bot-nonexistent")
        with self.assertRaises(multi_bot.BotRegistryError):
            multi_bot.delete_bot("0123456789abcdef", "wrong name")

    @patch.object(multi_bot.subprocess, "run")
    @patch.object(multi_bot, "get_metadata")
    @patch.object(multi_bot, "bot_path")
    def test_stop_failure_preserves_private_files(self, mock_path, mock_metadata, mock_run):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "0123456789abcdef"
            path.mkdir()
            (path / "bot-password.txt").write_text("private")
            mock_path.return_value = path
            mock_metadata.return_value = {"firstName": "Jolie", "lastName": "Candy"}
            mock_run.return_value = MagicMock(returncode=1)
            with self.assertRaisesRegex(multi_bot.BotRegistryError, "stop and disable"):
                multi_bot.delete_bot("0123456789abcdef", "Jolie Candy")
            self.assertTrue((path / "bot-password.txt").exists())


if __name__ == "__main__":
    unittest.main()
