# Stories Of Yggdrasil OSC Desktop v0.8.15

## Connection Reliability Repair

Designed for Sam.py OSC API 0.8.16 while retaining OSC API 0.8.13 as the minimum supported API.

- Pairing tokens remain intact during temporary network or API failures.
- Failed local `/sync` payloads are retained and retried so a temporary outage cannot silently discard the newest complete OSC state.
- Poll recovery is capped at 15 seconds with a 10-second default instead of backing off for up to 60 seconds.
- The first poll after an outage requests a full authoritative `/state` snapshot.
- The Dashboard distinguishes `CONNECTED`, `RECONNECTING`, `PAIRED`, and `OFF`.
- During an outage, DM Gate is shown as stale using the last authoritative OPEN/CLOSED state rather than being treated as a new gate change.
- Existing settings using the old 60-second maximum backoff migrate to 10 seconds.
- No Unity Tool or Contact changes are required.

Sam.py remains authoritative for combat state, DM Gate validation, damage, status, and character data.
