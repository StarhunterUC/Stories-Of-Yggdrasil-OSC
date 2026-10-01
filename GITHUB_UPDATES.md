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
