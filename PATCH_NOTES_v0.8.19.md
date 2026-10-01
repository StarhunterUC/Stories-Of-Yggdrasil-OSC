# Stories Of Yggdrasil OSC Desktop v0.8.19

## Windows TLS Trust Hardening

v0.8.19 fixes a class of one-machine HTTPS failures where Windows itself can validate the live Sam.py certificate but the frozen Desktop Python/OpenSSL runtime selects an obsolete certificate path and reports `CERTIFICATE_VERIFY_FAILED: certificate has expired`.

### Changed

- Sam.py API HTTPS uses the native Windows trust engine through `truststore`.
- GitHub update checks/downloads use the same hardened TLS context.
- Hostname validation and certificate verification remain required.
- TLS 1.2 is the minimum Desktop HTTPS protocol.
- A current `certifi` CA set is a verified fallback if native trust cannot initialize.
- Diagnostics exposes the TLS backend, native-trust state, verification policy, fallback state, and OpenSSL version.
- PyInstaller build output is deleted before every v0.8.19 build so stale SSL runtime files cannot contaminate a new release.

### Not changed

- Sam.py server-side TLS configuration.
- Pairing tokens or authentication.
- OSC API contract (minimum 0.8.13, recommended 0.8.18).
- v0.8.18 combat authority, damage attribution, NPC Mode, PvP handling, synchronization, or DM-gate behavior.

### Security

This patch does **not** use `verify=False`, an unverified SSL context, or an expired-certificate exception. Invalid, expired, untrusted, or hostname-mismatched certificates must still fail.
