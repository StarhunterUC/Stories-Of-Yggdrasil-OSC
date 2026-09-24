# GitHub Release Notes — v0.8.18

## Combat Authority / Contact Attribution Bridge

- Activates Sam.py v1.9.24 / OSC API v0.8.18 stat-aware combat events for incoming NPC → Player and attributed Player → Player Contacts.
- Adds live mapped-NPC and verified-PvP source selectors.
- Adds optional local VRChat identity sync and short-lived trusted `/soy/combat/*` source hints.
- Uses idempotent event IDs and preserves the same ID across a safe network retry.
- Restores one-second local Contact duplicate protection.
- Never trusts client-authored final Player damage/power and never guesses an unattributed remote Player.
- Keeps the existing verified NPC Mode Player → NPC route until outgoing attacker attribution can be proven from the attacking side.
- Preserves all v0.8.16 live-sync/reconnect repairs.

**Recommended server:** Sam.py v1.9.24 / OSC API v0.8.18.

The uploaded Desktop repository does not include the Unity Contact-generator source; `OSC_UNITY_COMBAT_BRIDGE_v0.8.18.md` documents the companion signals for that follow-up.
