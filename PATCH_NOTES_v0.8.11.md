# Stories Of Yggdrasil OSC Desktop v0.8.11

## Baseline

Built from the user-supplied `Stories-Of-Yggdrasil-OSC-Repo-Clean.zip`, confirmed as Desktop v0.8.10. Old VPS root uploads were not used as the Desktop source baseline.

## Player → NPC damage integration

- Added verified attacker identity to NPC Mode.
- Added separate player and character controls.
- Added manual entry fallback for API v0.8.13.
- Added optional roster population through API v0.8.14.
- Added explicit compatibility-fallback mode.
- Sync payloads contain only `npc_attacker_user_id` and `npc_attacker_char_name`.
- No Desktop ATK, MAG, SPD, level, equipment, license, or damage values are trusted.
- Compatibility mode sends empty identity fields to clear stale server selections.

## UI and diagnostics

- NPC preview now shows the combat stats used by the current Sam.py roster.
- Last-hit diagnostics show the server damage model, attacker status/stats, target DEF/RES, mitigation, tier, and final damage.
- The Desktop warns when the connected API is older than v0.8.13.
- The Desktop recommends v0.8.14 when attacker dropdowns are unavailable.
- Existing v0.8.10 NPC configurations migrate to explicit compatibility mode rather than silently pretending to use verified player stats.

## Unity Tool

No Unity damage-formula changes are required. Unity continues emitting canonical Weak, Average, Strong, and Critical Contacts. Player identity and all damage calculation remain in Desktop/Sam.py.

## Server companion

`server_companion/` contains an optional current-file patcher that upgrades OSC API v0.8.13 to v0.8.14 and adds a read-only attacker catalog to `/api/osc/npc/catalog`. It filters metadata records such as `dump`, exposes KO eligibility, creates a backup, compiles, and rolls back on failure.

## Validation

- Python compilation passed.
- 35 Desktop unit tests passed.
- Source audit passed.
- v0.8.14 companion dry-run passed against the current v5.23.43 Admin route structure with API v0.8.13 substituted as the expected live baseline.
- Windows PyInstaller executable was not cross-built in the Linux workspace; use the included Windows build script or GitHub release workflow.
