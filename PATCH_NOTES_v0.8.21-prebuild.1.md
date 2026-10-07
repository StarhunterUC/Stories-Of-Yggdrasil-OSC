# Stories Of Yggdrasil OSC Desktop v0.8.21-prebuild.1

Pre-build test client for the two-client combat/NPC investigation.

## Test changes

- Suppresses unchanged 20-second combat-catalog refresh messages from Recent Activity.
- Keeps catalog polling active; only a changed NPC/Player identity catalog is logged.
- Stops canonical SoY Friendly/Player contacts from being silently reclassified as NPC contacts merely because no PvP source was selected.
- Replaces the ambiguous NPC Mode checkbox workflow with explicit **Enable NPC Mode** and **Disable NPC Mode** actions.
- NPC Mode activation immediately forces Enemy alignment, persists the selected NPC, syncs with Sam.py, and requests the authoritative runtime state.
- NPC runtime activation no longer requires a Player -> NPC attacker to be preselected.
- Shows whether Sam.py has actually acknowledged the runtime as PLAYER or NPC, and names the active runtime profile.
- Keeps Sam.py authoritative for NPC HP/MP/stats and for all final combat resolution.

## Test targets

1. Alice -> Clover and Clover -> Alice, Friendly and Enemy states.
2. Enable Sythra Velisra NPC Mode and verify the runtime changes to the NPC HP/MP/stats.
3. Disable NPC Mode and verify the linked Player profile returns.
4. Confirm unchanged combat-catalog refreshes no longer spam Recent Activity.
5. Re-test Friendly harmful statuses, especially Sap. Sap is still expected to require a Sam.py/API-side fix if it bypasses alignment; this pre-build does not alter Sam.py.
