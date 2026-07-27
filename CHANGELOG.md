# Changelog

## v0.8.11 — Verified Player → NPC damage identity

- Adds an Attacking Player and Attacking Character workflow to Desktop NPC Mode.
- Sends only `npc_attacker_user_id` and `npc_attacker_char_name`; Sam.py remains authoritative for level, ATK, MAG, SPD, equipment, licenses, KO state, and final damage.
- Adds explicit **Verified stats** and **Compatibility fallback** modes so the fallback can no longer be mistaken for a real-player calculation.
- Displays NPC level, HP, MP, ATK, DEF, MAG, RES, SPD, EVA, VIT, affinities, weaknesses, and resistances from the Sam.py roster.
- Displays the last server-returned Player → NPC damage model, attacker stats, target DEF/RES, mitigation, attack tier, and final damage.
- Detects and warns about OSC API versions older than v0.8.13.
- Supports the optional OSC API v0.8.14 attacker roster while retaining manual Discord ID and character-name entry on v0.8.13.
- Preserves Desktop v0.8.10 polling, status authority, update, and single-instance behavior.
- Requires OSC API v0.8.13; OSC API v0.8.14 is recommended for populated player/character selectors. Unity Tool v0.5.8 TB6.2 remains supported and requires no damage-formula update.

## v0.8.10

- Adds revision-aware Sam.py state polling and lightweight unchanged responses.
- Uses adaptive idle and outage backoff to reduce HTTP/TLS and JSON work.
- Coalesces pending sync payloads instead of replaying stale intermediate states.
- Refreshes the Desktop UI and runtime_state.json only when authoritative values change.
- Rotates events.log and suppresses repeated outage messages.
- Prevents duplicate Desktop instances from creating a second poller or OSC port conflict.
- Requires OSC API v0.8.10; Unity Tool v0.5.8 TB6.2 remains supported.

## v0.8.9

- Makes Sam.py authoritative for real-time status timers and damage-over-time ticks.
- Prevents dead characters from sending local Spell or Technick actions.
- Uses a strict living-HP-below-15% Critical threshold.
- Replaces stale Desktop status mirrors atomically when Sam.py clears an effect.
- Displays Sam.py DoT tick, expiration, clear, and KO events once in Recent Activity.
- Requires OSC API v0.8.9 and recommends Unity Tool v0.5.8 TB6.2.

## v0.8.8

- Makes Sam.py authoritative for incoming melee and debuff Contacts.
- Adds Ally/Enemy source alignment for attacks and standalone debuffs.
- Uses final Base + Gear + Augment DEF, RES, EVA, VIT, and effective HP in damage resolution.
- Adds dynamic physical, magick, Technick, item, and damage-over-time handling.
- Rejects Friendly-to-Friendly harmful Contacts before HP or statuses change.
- Requires Unity Tool v0.5.6 and OSC API v0.8.8 for the complete alignment contract.

## v0.8.7

- Update checks now run automatically at startup and every six hours.
- A blank legacy GitHub repository setting is repaired automatically.
- Update downloads show live progress in the Desktop panel.
- The external installer now shows its own progress bar, verifies the installed version, writes an install log, and restarts the updated executable directly.
- Adds Desktop version metadata to Sam.py sync payloads.
- Supports standalone Item, Spell, and Technick workflows without requiring an active encounter.
- Requires Unity Tool v0.5.5 for Technick/Item caster-alignment Contacts.

# v0.8.6 — Enemy Alignment & NPC Mode

- Enemy Mode now syncs immediately and is protected from stale poll responses that previously turned it back off.
- Friendly harmful spell Contacts are rejected when the target is also friendly.
- Added Desktop NPC Mode with a searchable roster supplied by Sam.py's enemy catalog.
- NPC Mode uses a per-device runtime copy and never edits `data/enemies.json`.
- NPC Mode forces Enemy Mode on while active.

# Changelog

## v0.8.5 — Local action ownership, Technick gate diagnostics, and MP casting

- Separates local expression-menu actions from incoming Contact effects.
- Sends `SoY_SpellType` as `spell_cast_type`, so Sam.py charges the caster rather than the target.
- Sends `SoY_TechnickType` and `SoY_ItemType` as local use events.
- Keeps binary Spell/Technick/Item buses target-side and non-consuming.
- Displays distinct cast/use and incoming-contact results in Recent Activity.
- Requires OSC API v0.8.4.

# v0.8.4

- Marks decoded Spell, Technick, Item, hit, healing, damage, and status Contacts as VRChat-originated actions.
- RP Combat OFF now blocks every VRChat-triggered action before Sam.py HP, status, inventory, or encounter data can change.
- A closed Dungeon Master gate now blocks VRChat-triggered healing as well as damage, spells, Technicks, Items, and harmful statuses.
- The gate is scoped to VRChat triggers only; Discord combat, Player Panel, Admin Panel, Desktop Recovery, and ordinary Sam.py commands are unchanged.
- Added compact binary Technick and Item buses (`Active` plus `Bit0-7`).
- Added one-shot Technick and Item synchronization and authoritative VPS result logging.
- Requires OSC API v0.8.3 and Unity Contact Tool v0.5.4 for Technick/Item Contacts.

# v0.8.3

- Spell Contact IDs now trigger an immediate Sam.py sync instead of being activity-log-only telemetry.
- Spell IDs are consumed as one-shot events so later state syncs cannot re-cast a latched spell.
- Desktop activity now reports the authoritative VPS spell result and refreshed HP.
- Requires OSC API v0.8.2 for incoming healing, revival, and cleanse application.

# v0.8.2

- Added a conditional Curse Of Diablos meter to Character Overview, including 25%, 50%, 90%, and 98% warning states.
- Fixed the avatar radial gauge by converting Sam.py's authoritative 0..100 percentage into VRChat's normalized 0..1 Float range.
- Forces a Float OSC payload for `SoY_DiablosPercent`, including a safe `0.0` value.
- Rejects NaN, infinity, negative, and over-100 values before displaying or transmitting the gauge.
- Corrected the incoming radial echo conversion so `0.25` is recorded as 25%, not truncated to 0%.
- Requires OSC API v0.8.1 for expanded Curse Of Diablos status-shape detection.

# v0.8.1

- Added Unity Tool v0.5.3 binary spell Contact bus support.
- Added `SoY_SpellActive` and `SoY_SpellBit0` through `SoY_SpellBit7` inputs.
- Reconstructs stable spell IDs after a 30 ms packet-settle window.
- Preserves direct `SoY_SpellType` support for newer SDK receivers and old avatars.
- Added tests for Cure (`1`), Curaja (`4`), multi-bit spell ID `127`, and contact exit reset.
- VPS API v0.8.0 remains compatible because the Desktop submits the same resolved `spell_type` integer.

# v0.8.0

- Added Unity Tool v0.5.2 spell ID telemetry, Enemy Mode, Mist and Curse gauges.
- Added one-second contact invincibility-window synchronization.
- Added healing-rejection feedback and OSC API v0.8.0 support.

# Changelog

## 0.7.0

- Rebuilt the desktop interface around Overview, Recovery, Connection, and Settings.
- Added the Stories Of Yggdrasil application icon and version display.
- Removed debugging and manual-test pages from the normal interface.
- Added one-click environment preparation through `Start Stories OSC.bat`.
- Added Sam.py-authoritative Potion, Ether, revival-item, and restorative-magick controls.
- Added effective HP/MP, item-lore, equipment-potency, license, scroll, and Channeling support through the VPS API.
- Added GitHub Releases update checks with confirmation before download and installation.
- Added optional SHA-256 verification for release ZIPs.
- Updated generic compatible-avatar handling while preserving current contact and health parameter behavior.
