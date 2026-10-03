from __future__ import annotations

import ssl
import unittest
from unittest.mock import MagicMock, patch

from stories_yggdrasil_osc import tls_runtime
from stories_yggdrasil_osc.sam_client import SamClient


class TLSRuntimeV0819Tests(unittest.TestCase):
    def tearDown(self) -> None:
        tls_runtime._CONTEXT = None
        tls_runtime._STATUS = {
            "backend": "uninitialized",
            "native_windows_trust": False,
            "verification": "required",
            "minimum_tls": "TLSv1.2",
            "openssl_version": ssl.OPENSSL_VERSION,
            "fallback": False,
            "error": "",
        }

    def test_context_never_disables_certificate_verification(self) -> None:
        context = tls_runtime.get_ssl_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_diagnostics_report_verification_required(self) -> None:
        status = tls_runtime.tls_diagnostics()
        self.assertEqual(status["verification"], "required")
        self.assertIn("backend", status)
        self.assertIn("openssl_version", status)

    def test_sam_client_passes_hardened_context_to_urllib_fallback(self) -> None:
        queue_obj = MagicMock()
        client = SamClient(
            queue_obj,
            {
                "base_url":
                    "https://admin.storiesofyggdrasil.com/api/osc"
            },
        )

        fake_context = MagicMock(spec=ssl.SSLContext)

        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.geturl.return_value = (
            "https://admin.storiesofyggdrasil.com/api/osc/health"
        )
        response.read.return_value = b'{"ok": true}'
        response.headers = {"Content-Type": "application/json"}

        # v0.8.20 normally uses WinHTTP/Schannel on Windows.
        # Force WinHTTP unavailable here so this legacy test specifically
        # validates the hardened urllib/OpenSSL fallback path.
        with patch(
            "stories_yggdrasil_osc.sam_client.winhttp_available",
            return_value=False,
        ):
            with patch(
                "stories_yggdrasil_osc.sam_client.get_ssl_context",
                return_value=fake_context,
            ):
                with patch(
                    "stories_yggdrasil_osc.sam_client.urllib.request.urlopen",
                    return_value=response,
                ) as urlopen:
                    result = client._request("GET", "/health")

        self.assertTrue(result["ok"])
        self.assertIs(
            urlopen.call_args.kwargs["context"],
            fake_context,
        )


if __name__ == "__main__":
    unittest.main()