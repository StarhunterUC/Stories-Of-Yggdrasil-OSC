# GitHub Release Notes — v0.8.16

- Fixes stale Sam.py state that previously required **Reconnect All** after some edits/restarts.
- Detects a lower server revision after Sam.py restarts and automatically performs a full authoritative refresh.
- Rebases the revision cursor to the new process epoch instead of retaining an impossible older high-water mark.
- Adds quiet successful-poll heartbeats so `SAM CONNECTED` / `SYNC` stay accurate while state is unchanged.
- Defers complete remote poll snapshots while a local sync is awaiting acknowledgement, preventing one-shot `changed:true` updates from being partially consumed and lost.
- Keeps sync/test/pull failures in automatic `RECONNECTING` recovery.
- Detects Nginx maintenance-page redirects and non-JSON responses as temporary transport outages.
- OSC API v0.8.13 remains the minimum; v0.8.16+ is recommended.
- No Unity Tool/contact changes are required.
