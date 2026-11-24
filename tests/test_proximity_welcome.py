"""Per-avatar welcome configuration can be changed without touching other bots."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import control


class ProximityWelcomeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = self.root / "appsettings.json"
        self.cfg.write_text(json.dumps({
            "Grid": {"StartLocation": {"Mode": "Region", "RegionName": "Welcome",
                                       "Position": {"X": 128, "Y": 128, "Z": 25}}},
            "Bot": {"EnableIM": True, "EnableLocalChat": True, "ReconnectEnabled": True},
            "Ai": {"Enabled": True}
        }), encoding="utf-8")

    def values(self, **overrides):
        values = {"startMode": "region", "region": "Welcome", "x": 128,
                  "y": 128, "z": 25, "enableIM": True,
                  "enableLocalChat": True, "reconnectEnabled": True,
                  "welcomeEnabled": True, "welcomeRadius": 15,
                  "welcomeDelay": 30,
                  "welcomeMessage": "Welcome, {avatar_name}! Please IM me."}
        values.update(overrides)
        return values

    def test_defaults_off_then_save_and_reload(self):
        old = control.read_settings(self.root)
        self.assertFalse(old["welcomeEnabled"])
        self.assertIn("{avatar_name}", old["welcomeMessage"])
        result = control.save_settings(self.root, self.values())
        self.assertTrue(result["restartRequired"])
        saved = control.read_settings(self.root)
        self.assertTrue(saved["welcomeEnabled"])
        self.assertEqual(saved["welcomeRadius"], 15)
        self.assertEqual(saved["welcomeDelay"], 30)
        self.assertEqual(saved["welcomeMessage"], "Welcome, {avatar_name}! Please IM me.")
        self.assertTrue(json.loads(self.cfg.read_text())["Ai"]["Enabled"])

    def test_reject_unsafe_config_before_writing(self):
        initial = self.cfg.read_bytes()
        for change in (
            {"welcomeRadius": 90},
            {"welcomeDelay": 0},
            {"welcomeEnabled": "true"},
            {"welcomeMessage": ""},
            {"welcomeMessage": "X" * 651},
            {"welcomeMessage": "Line\x00break"},
            {"welcomeMessage": "🌙" * 190},
        ):
            with self.subTest(change=change):
                with self.assertRaises(control.ControlError):
                    control.save_settings(self.root, self.values(**change))
                self.assertEqual(self.cfg.read_bytes(), initial)

    def test_legacy_write_does_not_enable_welcome(self):
        values = self.values()
        for name in ("welcomeEnabled", "welcomeRadius", "welcomeDelay", "welcomeMessage"):
            del values[name]
        control.save_settings(self.root, values)
        self.assertFalse(control.read_settings(self.root)["welcomeEnabled"])


if __name__ == "__main__":
    unittest.main()
