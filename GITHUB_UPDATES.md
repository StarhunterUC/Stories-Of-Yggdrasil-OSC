# GitHub Release Notes — v0.8.20

## Windows-native Sam.py HTTPS

- Sam.py API calls now use Windows WinHTTP + Schannel directly on Windows.
- Fixes the remaining class of machines where Windows/PowerShell accepts the live Let’s Encrypt chain but the frozen Python/OpenSSL client still reports an expired certificate.
- TLS verification remains mandatory and authenticated Sam.py requests refuse redirects.
- Diagnostics now reports the active Sam.py HTTP transport.
- No Sam.py server/API deployment is required; OSC API v0.8.18 remains recommended.

---

# GitHub Release Notes — v0.8.19

## Windows TLS Trust Hardening

- Moves Sam.py API and updater HTTPS onto a shared verified TLS context.
- Uses the native Windows trust engine through `truststore` so the Desktop follows the same current certificate-chain decisions as Windows.
- Keeps certificate/hostname verification required and TLS 1.2+ enforced.
- Uses `certifi` only as a verified fallback.
- Adds TLS backend details to Diagnostics and support bundles.
- Forces a clean PyInstaller build to prevent stale `_ssl`/OpenSSL/CA files from surviving between releases.
- Keeps v0.8.18 combat authority and OSC API behavior unchanged.

**Recommended server:** OSC API v0.8.18. No Sam.py TLS change is required.
