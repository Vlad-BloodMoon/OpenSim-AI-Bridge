"""Regression tests for explicit region and OpenSimulator's server-side 'last' login."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import control


class StartLocationSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.install = Path(self.temp.name)
        (self.install / "appsettings.json").write_text(json.dumps({
            "Grid": {"StartLocation": {
                "Mode": "Region", "RegionName": "BloodMoon_Welcome",
                "Position": {"X": 350, "Y": 320, "Z": 125}}},
            "Bot": {"EnableIM": True, "EnableLocalChat": True, "ReconnectEnabled": True}
        }), encoding="utf-8")

    def values(self, **overrides):
        values = {"startMode": "region", "region": "BloodMoon_Welcome",
                  "x": 350, "y": 320, "z": 125,
                  "enableIM": True, "enableLocalChat": True,
                  "reconnectEnabled": True}
        values.update(overrides)
        return values

    def test_last_location_mode_persists_with_manual_coordinates(self):
        control.save_settings(self.install, self.values(startMode="last"))
        self.assertEqual(control.read_settings(self.install)["startMode"], "last")
        loc = json.loads((self.install / "appsettings.json").read_text())["Grid"]["StartLocation"]
        self.assertEqual(loc["Mode"], "Last")
        self.assertEqual(loc["RegionName"], "BloodMoon_Welcome")
        self.assertEqual(loc["Position"], {"X": 350, "Y": 320, "Z": 125})

    def test_switching_back_restores_manual_mode(self):
        control.save_settings(self.install, self.values(startMode="last"))
        control.save_settings(self.install, self.values(startMode="region"))
        self.assertEqual(control.read_settings(self.install)["startMode"], "region")

    def test_legacy_config_without_mode_stays_manual(self):
        file = self.install / "appsettings.json"
        data = json.loads(file.read_text())
        del data["Grid"]["StartLocation"]["Mode"]
        file.write_text(json.dumps(data))
        self.assertEqual(control.read_settings(self.install)["startMode"], "region")
        legacy = self.values()
        del legacy["startMode"]
        control.save_settings(self.install, legacy)
        self.assertEqual(control.read_settings(self.install)["startMode"], "region")

    def test_invalid_mode_rejected(self):
        with self.assertRaises(control.ControlError):
            control.save_settings(self.install, self.values(startMode="whatever"))


if __name__ == "__main__":
    unittest.main()
