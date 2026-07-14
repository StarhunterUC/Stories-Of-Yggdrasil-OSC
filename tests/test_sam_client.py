import queue
import unittest

from stories_yggdrasil_osc.sam_client import SamClient


class FakeClient(SamClient):
    def __init__(self):
        super().__init__(queue.Queue(), {"base_url": "https://example.invalid", "token": "token"})
        self.calls = []

    def _request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("payload")))
        if path == "/recovery/options":
            return {"options": []}
        if path == "/recovery/use":
            return {"message": "Potion used", "state": {}}
        return {"ok": True}


class SamClientTests(unittest.TestCase):
    def test_recovery_options_endpoint(self):
        client = FakeClient()
        client._do_command("recovery_options", {})
        self.assertEqual(client.calls[0][1], "/recovery/options")

    def test_recovery_use_endpoint(self):
        client = FakeClient()
        client._do_command("use_recovery", {"kind": "item", "name": "Potion"})
        self.assertEqual(client.calls[0][1], "/recovery/use")


if __name__ == "__main__":
    unittest.main()
