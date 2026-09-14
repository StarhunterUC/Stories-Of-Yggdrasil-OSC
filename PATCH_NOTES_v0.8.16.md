# Stories Of Yggdrasil OSC Desktop v0.8.16

## Live Sam.py Synchronization Repair

Desktop v0.8.16 repairs the state-refresh path that could leave the dashboard stale until **Reconnect All** was pressed.

- Detects when Sam.py restarts and its in-memory state revision returns to a lower value. The Desktop immediately performs a full authoritative `/state` refresh and rebases to the new revision epoch instead of waiting forever on an old larger revision.
- Full authoritative state responses replace the remembered revision rather than applying `max(old, new)`.
- Successful unchanged polls now emit a quiet heartbeat so the Dashboard's `SYNC` and `SAM CONNECTED` indicators remain fresh while the link is healthy.
- Poll state arriving while a local OSC change is waiting for `/sync` acknowledgement is deferred as one complete snapshot instead of partially consuming the revision and losing the only `changed:true` response.
- Poll events no longer clear the local `/sync` in-flight flag. Only the matching sync response/failure does.
- Temporary `/sync`, `/pull`, `/test`, and polling transport failures remain in `RECONNECTING` state and self-heal without revoking pairing.
- If Nginx redirects the OSC API to an HTML maintenance page, the Desktop detects that redirect/non-JSON response as a temporary transport outage instead of treating HTML as an API payload.
- Changing the configured Sam.py API base URL resets the revision cursor just like changing the pairing token.

Sam.py remains authoritative for combat, DM Gate, character data, effective stats, statuses, recovery, and combat actions. OSC API v0.8.13 remains the minimum supported API; v0.8.16 or newer is recommended.

### VPS/Nginx requirement

The human-facing Admin maintenance redirect must not intercept `/api/osc`. Give the OSC API its own Nginx location with `proxy_intercept_errors off`; allow only the browser-facing Admin page to redirect 502/503/504 responses to the main-site maintenance page.

No Unity Tool/contact changes are required.
