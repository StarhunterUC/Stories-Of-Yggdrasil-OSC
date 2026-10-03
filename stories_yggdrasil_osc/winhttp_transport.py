from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import urllib.parse
from dataclasses import dataclass
from typing import Mapping


class WinHttpUnavailable(RuntimeError):
    """Raised when the native Windows WinHTTP transport cannot be used."""


class WinHttpRequestError(RuntimeError):
    """Raised when WinHTTP fails before an HTTP response is available."""

    def __init__(self, message: str, *, code: int = 0) -> None:
        super().__init__(message)
        self.code = int(code or 0)


@dataclass(frozen=True)
class WinHttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]
    url: str


# winhttp.h constants used by the synchronous request path.
_WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY = 4
_WINHTTP_FLAG_SECURE = 0x00800000
_WINHTTP_OPTION_DISABLE_FEATURE = 63
_WINHTTP_DISABLE_REDIRECTS = 0x00000002
_WINHTTP_OPTION_SECURE_PROTOCOLS = 84
_WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2 = 0x00000800
_WINHTTP_QUERY_STATUS_CODE = 19
_WINHTTP_QUERY_CONTENT_TYPE = 1
_WINHTTP_QUERY_FLAG_NUMBER = 0x20000000

# Useful native error names for diagnostics. Certificate verification is never
# bypassed; these names simply make Schannel/WinHTTP failures intelligible.
_WINHTTP_ERRORS = {
    12002: "request timed out",
    12007: "server name could not be resolved",
    12029: "connection to server failed",
    12030: "connection was terminated",
    12037: "server certificate date is invalid",
    12038: "server certificate hostname is invalid",
    12044: "client certificate is required",
    12045: "server certificate authority is invalid",
    12057: "server certificate revocation check failed",
    12175: "secure TLS/Schannel handshake failed",
}


def available() -> bool:
    return os.name == "nt" and hasattr(ctypes, "WinDLL")


def _native_error(code: int, operation: str) -> WinHttpRequestError:
    detail = _WINHTTP_ERRORS.get(code)
    if not detail:
        try:
            detail = ctypes.FormatError(code).strip()
        except Exception:
            detail = "native WinHTTP error"
    return WinHttpRequestError(
        f"{operation} failed through Windows WinHTTP/Schannel: {detail} (WinError {code})",
        code=code,
    )


def request(
    url: str,
    *,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 10.0,
) -> WinHttpResponse:
    """Perform a verified HTTPS request with Windows WinHTTP + Schannel.

    This path intentionally does not expose any option for ignoring certificate
    failures. Automatic HTTP redirects are disabled so an Authorization header
    can never be silently forwarded outside the configured Sam.py endpoint.
    """
    if not available():
        raise WinHttpUnavailable("Windows WinHTTP transport is unavailable on this platform.")

    parsed = urllib.parse.urlsplit(str(url).strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("WinHTTP transport requires an https:// URL with a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials are not permitted inside the Sam.py API URL.")

    host = parsed.hostname
    port = int(parsed.port or 443)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    winhttp = ctypes.WinDLL("winhttp.dll", use_last_error=True)
    HINTERNET = ctypes.c_void_p
    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL
    LPCWSTR = wintypes.LPCWSTR
    LPVOID = wintypes.LPVOID

    winhttp.WinHttpOpen.argtypes = [LPCWSTR, DWORD, LPCWSTR, LPCWSTR, DWORD]
    winhttp.WinHttpOpen.restype = HINTERNET
    winhttp.WinHttpConnect.argtypes = [HINTERNET, LPCWSTR, wintypes.WORD, DWORD]
    winhttp.WinHttpConnect.restype = HINTERNET
    winhttp.WinHttpOpenRequest.argtypes = [
        HINTERNET,
        LPCWSTR,
        LPCWSTR,
        LPCWSTR,
        LPCWSTR,
        ctypes.POINTER(LPCWSTR),
        DWORD,
    ]
    winhttp.WinHttpOpenRequest.restype = HINTERNET
    winhttp.WinHttpSetTimeouts.argtypes = [HINTERNET, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    winhttp.WinHttpSetTimeouts.restype = BOOL
    winhttp.WinHttpSetOption.argtypes = [HINTERNET, DWORD, LPVOID, DWORD]
    winhttp.WinHttpSetOption.restype = BOOL
    winhttp.WinHttpSendRequest.argtypes = [HINTERNET, LPCWSTR, DWORD, LPVOID, DWORD, DWORD, ctypes.c_size_t]
    winhttp.WinHttpSendRequest.restype = BOOL
    winhttp.WinHttpReceiveResponse.argtypes = [HINTERNET, LPVOID]
    winhttp.WinHttpReceiveResponse.restype = BOOL
    winhttp.WinHttpQueryHeaders.argtypes = [HINTERNET, DWORD, LPCWSTR, LPVOID, ctypes.POINTER(DWORD), ctypes.POINTER(DWORD)]
    winhttp.WinHttpQueryHeaders.restype = BOOL
    winhttp.WinHttpQueryDataAvailable.argtypes = [HINTERNET, ctypes.POINTER(DWORD)]
    winhttp.WinHttpQueryDataAvailable.restype = BOOL
    winhttp.WinHttpReadData.argtypes = [HINTERNET, LPVOID, DWORD, ctypes.POINTER(DWORD)]
    winhttp.WinHttpReadData.restype = BOOL
    winhttp.WinHttpCloseHandle.argtypes = [HINTERNET]
    winhttp.WinHttpCloseHandle.restype = BOOL

    session = connect = request_handle = None
    try:
        session = winhttp.WinHttpOpen(
            "StoriesOfYggdrasilOSC/0.8.20",
            _WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY,
            None,
            None,
            0,
        )
        if not session:
            raise _native_error(ctypes.get_last_error(), "WinHttpOpen")

        timeout_ms = max(1000, min(300000, int(float(timeout) * 1000)))
        if not winhttp.WinHttpSetTimeouts(session, timeout_ms, timeout_ms, timeout_ms, timeout_ms):
            raise _native_error(ctypes.get_last_error(), "WinHttpSetTimeouts")

        # Restrict the WinHTTP session to TLS 1.2. Windows 10 supports this
        # protocol natively and Schannel still owns chain/hostname validation.
        protocols = DWORD(_WINHTTP_FLAG_SECURE_PROTOCOL_TLS1_2)
        if not winhttp.WinHttpSetOption(
            session,
            _WINHTTP_OPTION_SECURE_PROTOCOLS,
            ctypes.byref(protocols),
            ctypes.sizeof(protocols),
        ):
            raise _native_error(ctypes.get_last_error(), "WinHttpSetOption(TLS 1.2)")

        connect = winhttp.WinHttpConnect(session, host, port, 0)
        if not connect:
            raise _native_error(ctypes.get_last_error(), "WinHttpConnect")

        request_handle = winhttp.WinHttpOpenRequest(
            connect,
            str(method or "GET").upper(),
            path,
            None,
            None,
            None,
            _WINHTTP_FLAG_SECURE,
        )
        if not request_handle:
            raise _native_error(ctypes.get_last_error(), "WinHttpOpenRequest")

        # Never forward bearer auth via redirects. Sam.py's /api/osc endpoint is
        # expected to answer directly; any 30x is surfaced to the caller.
        disabled = DWORD(_WINHTTP_DISABLE_REDIRECTS)
        if not winhttp.WinHttpSetOption(
            request_handle,
            _WINHTTP_OPTION_DISABLE_FEATURE,
            ctypes.byref(disabled),
            ctypes.sizeof(disabled),
        ):
            raise _native_error(ctypes.get_last_error(), "WinHttpSetOption(redirects)")

        header_map = {str(k): str(v) for k, v in (headers or {}).items()}
        header_text = "".join(f"{key}: {value}\r\n" for key, value in header_map.items())
        header_len = len(header_text) if header_text else 0

        payload = bytes(body or b"")
        payload_buffer = ctypes.create_string_buffer(payload, len(payload)) if payload else None
        payload_ptr = ctypes.cast(payload_buffer, LPVOID) if payload_buffer is not None else None

        if not winhttp.WinHttpSendRequest(
            request_handle,
            header_text if header_text else None,
            header_len,
            payload_ptr,
            len(payload),
            len(payload),
            0,
        ):
            raise _native_error(ctypes.get_last_error(), "WinHttpSendRequest")

        if not winhttp.WinHttpReceiveResponse(request_handle, None):
            raise _native_error(ctypes.get_last_error(), "WinHttpReceiveResponse")

        status = DWORD(0)
        status_size = DWORD(ctypes.sizeof(status))
        index = DWORD(0)
        if not winhttp.WinHttpQueryHeaders(
            request_handle,
            _WINHTTP_QUERY_STATUS_CODE | _WINHTTP_QUERY_FLAG_NUMBER,
            None,
            ctypes.byref(status),
            ctypes.byref(status_size),
            ctypes.byref(index),
        ):
            raise _native_error(ctypes.get_last_error(), "WinHttpQueryHeaders(status)")

        response_headers: dict[str, str] = {}
        content_type_size = DWORD(0)
        ctypes.set_last_error(0)
        winhttp.WinHttpQueryHeaders(
            request_handle,
            _WINHTTP_QUERY_CONTENT_TYPE,
            None,
            None,
            ctypes.byref(content_type_size),
            None,
        )
        if content_type_size.value:
            char_count = max(1, content_type_size.value // ctypes.sizeof(ctypes.c_wchar))
            content_type_buf = ctypes.create_unicode_buffer(char_count)
            if winhttp.WinHttpQueryHeaders(
                request_handle,
                _WINHTTP_QUERY_CONTENT_TYPE,
                None,
                content_type_buf,
                ctypes.byref(content_type_size),
                None,
            ):
                response_headers["Content-Type"] = content_type_buf.value

        chunks: list[bytes] = []
        while True:
            available_bytes = DWORD(0)
            if not winhttp.WinHttpQueryDataAvailable(request_handle, ctypes.byref(available_bytes)):
                raise _native_error(ctypes.get_last_error(), "WinHttpQueryDataAvailable")
            if not available_bytes.value:
                break
            buffer = ctypes.create_string_buffer(available_bytes.value)
            read = DWORD(0)
            if not winhttp.WinHttpReadData(
                request_handle,
                buffer,
                available_bytes.value,
                ctypes.byref(read),
            ):
                raise _native_error(ctypes.get_last_error(), "WinHttpReadData")
            if read.value:
                chunks.append(buffer.raw[: read.value])

        return WinHttpResponse(
            status=int(status.value),
            body=b"".join(chunks),
            headers=response_headers,
            url=urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, "")),
        )
    finally:
        for handle in (request_handle, connect, session):
            if handle:
                try:
                    winhttp.WinHttpCloseHandle(handle)
                except Exception:
                    pass
