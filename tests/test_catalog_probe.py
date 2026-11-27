"""Offline manual API probe tests: no HTTP, no keys retained, no routing."""
import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "controller"))
import catalog_probe


def snapshot():
    return {"models": [
        {"provider": "cerebras", "model": "llama-3.3-70b"},
        {"provider": "cohere", "model": "command-a-03-2025"},
        {"provider": "not-allowed", "model": "evil"}
    ]}


class FakeResponse:
    status = 200
    headers = {"Content-Length": "64"}

    def __init__(self, data):
        self._stream = io.BytesIO(data)

    def read(self, n):
        return self._stream.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeOpener:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append((req, timeout))
        if self.error:
            raise self.error
        return FakeResponse(self.data)


class ProbeTests(unittest.TestCase):
    def test_success_only_curated_endpoint_and_one_request(self):
        content = b'{"choices":[{"message":{"content":"BONJOUR"}}]}'
        opener = FakeOpener(content)
        result = catalog_probe.probe("cerebras", "llama-3.3-70b", "sample-private-key", snapshot(), opener)
        self.assertTrue(result["success"])
        self.assertFalse(result["routingEnabled"])
        self.assertFalse(result["credentialsStored"])
        self.assertNotIn("sample-private-key", json.dumps(result))
        self.assertEqual(len(opener.calls), 1)
        req, timeout = opener.calls[0]
        self.assertEqual(req.full_url, "https://api.cerebras.ai/v1/chat/completions")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(timeout, 12)
        self.assertIn(b"llama-3.3-70b", req.data)

    def test_no_unreviewed_endpoint_or_model_or_bad_key(self):
        for provider, model, key in [
            ("not-allowed", "evil", "key"),
            ("cerebras", "unknown", "key"),
            ("cerebras", "../../etc/passwd", "key"),
            ("cohere", "command-a-03-2025", "bad\nkey"),
            ("cerebras", "llama-3.3-70b", "")
        ]:
            opener = FakeOpener()
            with self.assertRaises(catalog_probe.ProbeError):
                catalog_probe.probe(provider, model, key, snapshot(), opener)
            self.assertEqual(opener.calls, [])

    def test_http_error_is_sanitized_and_no_response_leaks(self):
        opener = FakeOpener(error=urllib.error.HTTPError(
            "https://api.cerebras.ai", 401, "private-key-in-error",
            {}, io.BytesIO(b"secret data")))
        with self.assertRaisesRegex(catalog_probe.ProbeError, "401"):
            catalog_probe.probe("cerebras", "llama-3.3-70b", "sample", snapshot(), opener)

    def test_200_without_openai_text_is_not_success(self):
        opener = FakeOpener(b'{"candidates":[{"text":"unexpected"}]}')
        with self.assertRaisesRegex(catalog_probe.ProbeError, "incompatible"):
            catalog_probe.probe("cerebras", "llama-3.3-70b", "sample", snapshot(), opener)


if __name__ == "__main__":
    unittest.main()
