# Stories Of Yggdrasil OSC Desktop v0.8.20

## Native Windows Sam.py HTTPS transport

v0.8.20 addresses the remaining one-machine SSL failure after v0.8.19. The affected Windows PC can verify the live Sam.py HTTPS endpoint through PowerShell/Windows, while the frozen Python client still reports `CERTIFICATE_VERIFY_FAILED: certificate has expired`.

### Changed

- Sam.py API requests on Windows now use `winhttp.dll` directly through a small ctypes transport.
- WinHTTP uses Windows Schannel and the operating system certificate-chain engine instead of Python/OpenSSL for Sam.py HTTPS.
- System/per-user proxy discovery is handled through `WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY`.
- TLS 1.2 is required on the native path for Windows 10 compatibility.
- Certificate verification and hostname verification remain mandatory; there is no certificate-ignore mode.
- Automatic redirects are disabled for authenticated Sam.py requests so bearer tokens cannot be forwarded outside the configured API endpoint.
- Diagnostics reports `sam_http_transport` and `sam_http_native`.
- Non-Windows source runs retain the existing verified urllib/OpenSSL transport.

### Unchanged

- Sam.py itself is not changed.
- OSC API minimum remains v0.8.13 and v0.8.18 remains recommended.
- Combat authority, pairing, reconnect, NPC attribution, and OSC behavior are unchanged.
