"""Private per-avatar provider activity must remain free of IM text and secrets."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import control


class ProviderActivityTests(unittest.TestCase):
    def test_empty_and_separate_bot_histories(self):
        with tempfile.TemporaryDirectory() as directory:
            primary = Path(directory) / "main"
            secondary = Path(directory) / "secondary"
            (primary / "data").mkdir(parents=True)
            (secondary / "data").mkdir(parents=True)
            self.assertEqual(control.read_ai_activity(primary), {"events": []})
            events = [
                {"utc": "2026-11-27T10:20:30Z", "provider": "Groq",
                 "model": "openai/gpt-oss-20b", "outcome": "http_error",
                 "httpStatus": 429, "switched": False},
                {"utc": "2026-11-27T10:20:32Z", "provider": "Gemini",
                 "model": "gemini-3.5-flash-lite", "outcome": "success",
                 "httpStatus": 200, "switched": True,
                 "durationMs": 845, "reason": None, "cooldownUntilUtc": None},
            ]
            (primary / "data" / "ai-provider-activity.json").write_text(
                json.dumps(events), encoding="utf-8")
            view = control.read_ai_activity(primary)
            self.assertEqual(len(view["events"]), 2)
            self.assertEqual(view["events"][0]["provider"], "Gemini")
            self.assertTrue(view["events"][0]["switched"])
            self.assertEqual(view["events"][0]["durationMs"], 845)
            self.assertIsNone(view["events"][0]["reason"])
            self.assertIsNone(view["events"][1]["durationMs"])  # old bot format
            self.assertEqual(control.read_ai_activity(secondary), {"events": []})

    def test_cooldown_event_exposes_only_bounded_approved_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = Path(directory)
            (bot / "data").mkdir()
            (bot / "data" / "ai-provider-activity.json").write_text(json.dumps([{
                "utc": "2026-11-27T12:00:00.0000000+00:00",
                "provider": "Groq", "model": "openai/gpt-oss-20b",
                "outcome": "http_error", "httpStatus": 429,
                "switched": False, "durationMs": 1333,
                "reason": "rate_limit",
                "cooldownUntilUtc": "2026-11-27T12:03:00.0000000+00:00",
                "prompt": "private", "token": "private"
            }]), encoding="utf-8")
            event = control.read_ai_activity(bot)["events"][0]
            self.assertEqual(event["reason"], "rate_limit")
            self.assertEqual(event["durationMs"], 1333)
            self.assertEqual(event["cooldownUntilUtc"],
                             "2026-11-27T12:03:00.0000000+00:00")
            self.assertNotIn("prompt", event)
            self.assertNotIn("token", event)

    def test_unsafe_file_refused_and_unapproved_fields_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            bot = Path(directory) / "bot"
            (bot / "data").mkdir(parents=True)
            source = bot / "data" / "ai-provider-activity.json"
            source.write_text(json.dumps([{
                "utc": "2026-11-27T10:20:32Z", "provider": "Groq",
                "model": "openai/gpt-oss-20b", "outcome": "success",
                "httpStatus": 200, "switched": False,
                "durationMs": 250, "reason": "unapproved secret text",
                "cooldownUntilUtc": "not-an-utc-date",
                "secretKey": "should-not-leak", "residentIM": "private message"
            }]))
            view = control.read_ai_activity(bot)
            self.assertNotIn("secretKey", view["events"][0])
            self.assertNotIn("residentIM", view["events"][0])
            self.assertEqual(view["events"][0]["durationMs"], 250)
            self.assertIsNone(view["events"][0]["reason"])
            self.assertIsNone(view["events"][0]["cooldownUntilUtc"])
            source.unlink()
            source.symlink_to(Path(directory) / "outside")
            with self.assertRaises(control.ControlError):
                control.read_ai_activity(bot)


if __name__ == "__main__":
    unittest.main()
