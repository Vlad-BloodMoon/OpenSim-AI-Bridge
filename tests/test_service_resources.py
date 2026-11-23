import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import control


class ResourceUsageTests(unittest.TestCase):
    def setUp(self):
        control._CPU_SAMPLES.clear()

    def test_first_sample_cpu_unavailable_and_memory_converted(self):
        r = control.resource_usage("opensim-ai-bridge.service", "active",
                                   {"MemoryCurrent": str(80 * 1024 * 1024), "CPUUsageNSec": "500000000"}, now=10)
        self.assertEqual(r["memoryMb"], 80.0)
        self.assertIsNone(r["cpuPercent"])

    def test_cpu_percentage_over_ten_seconds(self):
        unit = "opensim-ai-bridge.service"
        control.resource_usage(unit, "active", {"MemoryCurrent": "104857600", "CPUUsageNSec": "1000000000"}, now=10)
        r = control.resource_usage(unit, "active",
                                   {"MemoryCurrent": "104857600", "CPUUsageNSec": "3500000000"}, now=20)
        self.assertEqual(r, {"memoryMb": 100.0, "cpuPercent": 25.0})

    def test_multiple_cores_can_exceed_one_hundred_percent(self):
        unit = "opensim-ai-bridge@0123456789abcdef.service"
        control.resource_usage(unit, "active", {"MemoryCurrent": "0", "CPUUsageNSec": "0"}, now=10)
        r = control.resource_usage(unit, "active",
                                   {"MemoryCurrent": "0", "CPUUsageNSec": "20000000000"}, now=20)
        self.assertEqual(r["cpuPercent"], 200.0)

    def test_restart_resets_cpu_counter(self):
        unit = "opensim-ai-bridge.service"
        control.resource_usage(unit, "active", {"MemoryCurrent": "0", "CPUUsageNSec": "4000000000"}, now=10)
        r = control.resource_usage(unit, "active", {"MemoryCurrent": "0", "CPUUsageNSec": "1000000"}, now=20)
        self.assertIsNone(r["cpuPercent"])

    def test_stopped_or_missing_metrics(self):
        unit = "opensim-ai-bridge.service"
        self.assertEqual(control.resource_usage(unit, "inactive", {}, now=30),
                         {"memoryMb": None, "cpuPercent": None})
        self.assertEqual(control.resource_usage(unit, "active",
                         {"MemoryCurrent": "[not set]", "CPUUsageNSec": "18446744073709551615"}, now=40),
                         {"memoryMb": None, "cpuPercent": None})

    @patch.object(control, "systemctl", return_value="ActiveState=active\nSubState=running\nUnitFileState=enabled\nMemoryCurrent=104857600\nCPUUsageNSec=500000000\n")
    def test_metrics_only_when_requested(self, mock_systemctl):
        result = control.service_state(with_metrics=True)
        self.assertEqual(result["resources"]["memoryMb"], 100.0)
        self.assertIn("CPUUsageNSec", mock_systemctl.call_args.args[1])
        result = control.service_state()
        self.assertNotIn("resources", result)
