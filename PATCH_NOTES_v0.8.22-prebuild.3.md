# Stories Of Yggdrasil OSC v0.8.22-prebuild.3 — NPC HP repair

- NPC Mode can no longer overwrite a selected NPC's HP with previously linked Player HP via passive /sync.
- Roster selections in active NPC Mode rebind to a new server runtime and wait for acknowledgement.
- Adds **Restore Full NPC HP** in NPC Mode, enabled only when Sam.py confirms the exact selected NPC runtime and missing HP. Uses a confirmed user action and the existing authenticated /sync route, not Player recovery items.
- The client checks the server-returned state before reporting restoration success.
- NPC MP recovery is not included without server support.
- Keeps Protocol 21 / TB18, previous crash diagnostics, and v0.8.21 stable unchanged.
