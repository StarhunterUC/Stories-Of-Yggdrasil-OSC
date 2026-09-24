# Stories Of Yggdrasil OSC Desktop v0.8.18
## Sam.py Combat Authority / Contact Attribution Bridge

Desktop v0.8.18 activates the OSC combat-authority API introduced by Sam.py v1.9.24 / OSC API v0.8.18 without moving combat math back into the client.

### Added

- Fetches `GET /api/osc/combat/catalog` while RP Combat is active.
- Submits attributed incoming Player-target Contacts to `POST /api/osc/combat/event`.
- Generates one unique `event_id` per Contact and reuses that exact ID for a single safe transport retry.
- Never supplies arbitrary numeric Player Contact power; Sam.py remains authoritative for final damage/healing.
- Syncs the local Player's optional `vrchat_user_id`, VRChat display name, and current Avatar ID through the existing `/sync` path.
- Adds **Incoming Contact Attribution** selectors for:
  - mapped NPC → Player sources;
  - verified Player → Player sources published by Sam.py.
- Defaults an otherwise unclassified damaging model to **Enemy** when no verified PvP source is selected, matching the current SoY rule. It still refuses to guess *which* enemy profile caused the hit.
- Adds short-lived trusted-local identity-hint OSC inputs under `/soy/combat/...` for a future Unity/world companion bridge.
- Restores the one-second local Contact i-frame/debounce before an authoritative request is sent, preventing rapid duplicate Contact pulses from becoming separate server events.

### Preserved intentionally

- **NPC Mode Player → NPC Contacts remain on the existing verified target-reported route.** The v0.8.18 combat endpoint expects this direction to be reported by the attacking Player's linked Desktop. Replacing the current NPC Mode route without a reliable outgoing-attacker bridge would lose identity rather than improve it.
- Spell, Technick, Item, status, recovery, normal Sam.py state synchronization, maintenance recovery, and v0.8.16 revision-epoch handling are unchanged.
- A combat-catalog failure falls back to the existing legacy Contact sync path rather than breaking all combat.

### Attribution safety

Raw avatar Contact pulses are not treated as proof of a remote Player identity. For PvP the Desktop uses only a Sam.py-published verified Player identity selection or a fresh trusted-local identity hint. If the source cannot be attributed safely, the hit is held and logged instead of guessing a Player.

For NPC → Player, the selected/hinted Avatar ID is still validated by Sam.py against its NPC Avatar bindings before damage can be registered.

### Unity / world bridge follow-up

The uploaded repository is the Windows OSC Desktop source. It does not contain the SoY Unity Contact generator/tool source, so this release adds the Desktop side of the integration plus the input contract for a future Unity/world companion update. See `OSC_UNITY_COMBAT_BRIDGE_v0.8.18.md`.

### Server requirements

- Minimum API for legacy Desktop operation: **v0.8.13**
- Recommended / required for the new combat-authority path: **v0.8.18**
- Matching Sam.py release: **v1.9.24**

### Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe audit_source.py
```
