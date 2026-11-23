import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import control


class FleetTests(unittest.TestCase):
    @patch.object(control.multi_bot, "instances", return_value=["0123456789abcdef", "fedcba9876543210"])
    def test_only_known_services(self, _mock_instances):
        self.assertEqual(control.fleet_units(), [
            "opensim-ai-bridge.service",
            "opensim-ai-bridge@0123456789abcdef.service",
            "opensim-ai-bridge@fedcba9876543210.service",
        ])

    def test_confirmation_required_for_global_stop(self):
        with self.assertRaises(control.ControlError):
            control.fleet_stop(False)

    def test_confirmation_required_for_global_resume(self):
        with self.assertRaises(control.ControlError):
            control.fleet_resume(False, Path("/tmp/never-accessed"))

    @patch.object(control, "FLEET_LOCK")
    def test_global_lock_blocks_bot_restart(self, mock_lock):
        mock_lock.exists.return_value = True
        with self.assertRaisesRegex(control.ControlError, "Global maintenance"):
            control.execute("start", Path("/tmp/never-accessed"), False, Path("/tmp/never-accessed"))
        with self.assertRaisesRegex(control.ControlError, "Global maintenance"):
            control.execute("create_bot", Path("/tmp/never-accessed"), False, Path("/tmp/never-accessed"), credentials={})


if __name__ == "__main__":
    unittest.main()
