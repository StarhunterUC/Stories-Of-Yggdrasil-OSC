from __future__ import annotations

import json
import queue
import unittest
from unittest import mock

from stories_yggdrasil_osc.sam_client import SamClient
from stories_yggdrasil_osc.winhttp_transport import WinHttpRequestError, WinHttpResponse


class WinHttpTransportV0820Tests(unittest.TestCase):
    def test_windows_native_transport_is_preferred_for_sam(self) -> None:
        client = SamClient(queue.Queue(), {"base_url": "https://admin.storiesofyggdrasil.com/api/osc"})
        payload = {"ok": True, "version": "0.8.18"}
        response = WinHttpResponse(
            status=200,
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            url="https://admin.storiesofyggdrasil.com/api/osc/health",
        )
        with mock.patch("stories_yggdrasil_osc.sam_client.winhttp_available", return_value=True), mock.patch(
            "stories_yggdrasil_osc.sam_client.winhttp_request", return_value=response
        ) as native, mock.patch("stories_yggdrasil_osc.sam_client.urllib.request.urlopen") as urllib_open:
            result = client._request("GET", "/health")
        self.assertEqual(result, payload)
        native.assert_called_once()
        urllib_open.assert_not_called()

    def test_native_certificate_error_is_not_bypassed(self) -> None:
        client = SamClient(queue.Queue(), {"base_url": "https://admin.storiesofyggdrasil.com/api/osc"})
        with mock.patch("stories_yggdrasil_osc.sam_client.winhttp_available", return_value=True), mock.patch(
            "stories_yggdrasil_osc.sam_client.winhttp_request",
            side_effect=WinHttpRequestError("server certificate date is invalid", code=12037),
        ):
            with self.assertRaisesRegex(RuntimeError, "Windows WinHTTP/Schannel"):
                client._request("GET", "/health")

    def test_native_redirect_is_refused(self) -> None:
        client = SamClient(queue.Queue(), {"base_url": "https://admin.storiesofyggdrasil.com/api/osc"})
        response = WinHttpResponse(
            status=302,
            body=b"",
            headers={},
            url="https://admin.storiesofyggdrasil.com/api/osc/health",
        )
        with mock.patch("stories_yggdrasil_osc.sam_client.winhttp_available", return_value=True), mock.patch(
            "stories_yggdrasil_osc.sam_client.winhttp_request", return_value=response
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                client._request("GET", "/health")


if __name__ == "__main__":
    unittest.main()
