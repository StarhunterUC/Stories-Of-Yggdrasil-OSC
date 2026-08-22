# GitHub Release Notes — v0.8.15

- Preserves pairing during temporary Sam.py/VPS/API outages.
- Retains failed local sync payloads and retries the newest complete state after recovery.
- Caps reconnect backoff at 15 seconds with a 10-second default.
- Forces a full authoritative Sam.py state refresh immediately after an outage.
- Adds explicit CONNECTED, RECONNECTING, PAIRED, and OFF dashboard states.
- Shows DM Gate as STALE with the last authoritative state during outages.
- Migrates legacy 60-second maximum backoff settings to 10 seconds.
- Recommends Sam.py OSC API v0.8.16; OSC API v0.8.13 remains the minimum.
- No Unity Tool/contact changes are required.
