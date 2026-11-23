import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import multi_bot


class BotValidationTests(unittest.TestCase):
    def valid(self):
        return {"firstName": "Test", "lastName": "Resident", "password": "example-private-secret",
                "region": "BloodMoon_TEST", "x": 128, "y": 128, "z": 25}

    def test_valid(self):
        self.assertEqual(multi_bot.validate_create(self.valid())["region"], "BloodMoon_TEST")

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
        for field, value in (("x", -1), ("y", 257), ("z", 4097), ("x", True), ("y", 5.2)):
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


if __name__ == "__main__":
    unittest.main()
