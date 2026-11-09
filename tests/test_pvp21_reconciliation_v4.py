import queue
import unittest
from unittest.mock import patch

from stories_yggdrasil_osc.sam_client import SamClient


class Pvp21ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.client = SamClient(queue.Queue(), {"enabled": True, "token": "test"})
        self.responses = []
        self.calls = []
        self.client._request = self.fake_request

    def fake_request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs.get("payload")))
        return self.responses.pop(0)

    def test_pending_then_replay_success_keeps_id_and_direction(self):
        self.responses = [
            {"ok": True, "pending": True, "applied": False},
            {"ok": True, "pending": False, "applied": True, "damage": 12},
        ]
        with patch("stories_yggdrasil_osc.sam_client.time.monotonic",
                   side_effect=[1.0, 1.0, 1.5]):
            self.client._do_command("pvp_attack_attempt", {
                "tier": "strong", "event_id": "a-1"})
            tracked = dict(self.client._pvp_pending["a-1"])
            self.client._do_command("pvp_recheck", tracked)
        self.assertNotIn("a-1", self.client._pvp_pending)
        self.assertEqual(self.calls[0], self.calls[1])
        event = self.client.event_queue.get_nowait()
        self.assertEqual(event.kind, "pvp_handshake")
        self.assertTrue(event.data["applied"])

    def test_receipt_replays_receipt_not_attempt(self):
        self.responses = [
            {"ok": True, "pending": True},
            {"ok": True, "pending": False, "applied": False, "message": "Evaded"},
        ]
        with patch("stories_yggdrasil_osc.sam_client.time.monotonic",
                   side_effect=[1.0, 1.0, 1.5]):
            self.client._do_command("pvp_hit_receipt", {
                "tier": "weak", "event_id": "r-1"})
            self.client._do_command("pvp_recheck",
                                    dict(self.client._pvp_pending["r-1"]))
        self.assertEqual([x[1] for x in self.calls],
                         ["/pvp/receipt", "/pvp/receipt"])
        self.assertEqual(self.calls[0][2], {"tier": "weak", "event_id": "r-1"})

    def test_pending_replay_times_out_without_new_event(self):
        self.responses = [{"pending": True}, {"pending": True}]
        with patch("stories_yggdrasil_osc.sam_client.time.monotonic",
                   side_effect=[1.0, 1.0, 5.0]):
            self.client._do_command("pvp_attack_attempt", {
                "tier": "average", "event_id": "a-2"})
            self.client._do_command("pvp_recheck",
                                    dict(self.client._pvp_pending["a-2"]))
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0], self.calls[1])
        self.assertEqual(self.client.event_queue.get_nowait().data["reason_code"],
                         "unconfirmed_timeout")
        self.assertEqual(self.client._pvp_pending, {})

    def test_reconfigure_new_token_discards_old_pending_replays(self):
        self.client._pvp_pending["old"] = {"event_id": "old"}
        self.client.reconfigure({"enabled": True, "token": "new"})
        self.assertEqual(self.client._pvp_pending, {})


if __name__ == "__main__":
    unittest.main()
