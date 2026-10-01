from __future__ import annotations

import os
import ssl
import threading
from typing import Any

_LOCK = threading.RLock()
_CONTEXT: ssl.SSLContext | None = None
_STATUS: dict[str, Any] = {
    "backend": "uninitialized",
    "native_windows_trust": False,
    "verification": "required",
    "minimum_tls": "TLSv1.2",
    "openssl_version": ssl.OPENSSL_VERSION,
    "fallback": False,
    "error": "",
}


def _require_verified_context(context: ssl.SSLContext) -> ssl.SSLContext:
    """Apply the Desktop's minimum TLS policy without disabling verification."""
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _build_context() -> tuple[ssl.SSLContext, dict[str, Any]]:
    native_error = ""

    # Windows players should use the same native certificate chain engine that
    # PowerShell/WinHTTP/Schannel uses.  This avoids a frozen Python/OpenSSL CA
    # bundle selecting an obsolete intermediate when Windows already has a
    # current valid chain for Sam.py.
    if os.name == "nt":
        try:
            import truststore

            context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            _require_verified_context(context)
            return context, {
                "backend": "Windows Trust Store (truststore)",
                "native_windows_trust": True,
                "verification": "required",
                "minimum_tls": "TLSv1.2",
                "openssl_version": ssl.OPENSSL_VERSION,
                "fallback": False,
                "error": "",
            }
        except Exception as exc:
            native_error = f"{type(exc).__name__}: {exc}"

    # A current bundled Mozilla CA set is a verified fallback only.  This is
    # intentionally NOT an unverified SSL context and never uses verify=False.
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
        _require_verified_context(context)
        return context, {
            "backend": "Bundled CA fallback (certifi)",
            "native_windows_trust": False,
            "verification": "required",
            "minimum_tls": "TLSv1.2",
            "openssl_version": ssl.OPENSSL_VERSION,
            "fallback": True,
            "error": native_error,
        }
    except Exception as exc:
        fallback_error = f"{type(exc).__name__}: {exc}"

    # Last-resort verified platform/Python defaults.  Keeping this path allows
    # source runs on non-Windows systems without ever weakening TLS validation.
    context = ssl.create_default_context()
    _require_verified_context(context)
    combined = "; ".join(part for part in (native_error, fallback_error) if part)
    return context, {
        "backend": "Python/OpenSSL verified defaults",
        "native_windows_trust": False,
        "verification": "required",
        "minimum_tls": "TLSv1.2",
        "openssl_version": ssl.OPENSSL_VERSION,
        "fallback": True,
        "error": combined,
    }


def configure_tls_runtime() -> dict[str, Any]:
    """Initialize the verified TLS context once and return safe diagnostics."""
    global _CONTEXT, _STATUS
    with _LOCK:
        if _CONTEXT is None:
            _CONTEXT, _STATUS = _build_context()
        return dict(_STATUS)


def get_ssl_context() -> ssl.SSLContext:
    """Return the shared verified TLS context used for all HTTPS requests."""
    configure_tls_runtime()
    assert _CONTEXT is not None
    return _CONTEXT


def tls_diagnostics() -> dict[str, Any]:
    """Return non-secret TLS runtime details for Desktop diagnostics/support."""
    return configure_tls_runtime()
