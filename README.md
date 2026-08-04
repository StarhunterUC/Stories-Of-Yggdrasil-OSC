# Stories Of Yggdrasil OSC v0.8.14

A streamlined Windows desktop bridge between VRChat OSC and the VPS-hosted Sam.py system.


## v0.8.14

Desktop v0.8.14 keeps Sam.py authoritative while making the program easier to use during VRChat sessions. The global header shows Sam.py, VRChat, avatar, RP Combat, Dungeon Master Gate, API, and sync status on every page. Actions can be searched, filtered, favorited, and reviewed with exact availability reasons. Recent Activity supports filtering, search, pause, duplicate grouping, encounter-cleanup suppression, and copy controls. NPC Mode adds search and favorites. Window state and UI preferences persist automatically, and Diagnostics can generate a sanitized support bundle.


## v0.8.12 verified Player → NPC damage

NPC Mode now identifies the player and exact Sam.py character attacking the selected NPC. The Desktop sends identity only; Sam.py retrieves the live character record and calculates damage from the player's current level and offensive stats against the NPC runtime's authoritative level, DEF, RES, EVA, VIT, and affinities.

In **Settings → NPC Mode**:

1. Select and enable the NPC runtime profile.
2. Select **Verified stats**.
3. Choose the attacking player and character from the roster, or enter the numeric Discord ID and exact character name manually.
4. Save Settings.

OSC API v0.8.13 supports verified identity through manual entry. The optional v0.8.14 companion patch adds the populated attacker roster to the existing authenticated NPC catalog. **Compatibility fallback** remains available as an explicit mode for transition testing; it does not use a real player's combat stats.

The last server-resolved Player → NPC hit is displayed with its damage model, attacker ATK/MAG/SPD, target DEF/RES, mitigation, attack tier, and final damage. The Desktop never submits trusted combat attributes.

## v0.8.10 Phase 1 runtime efficiency

Desktop v0.8.10 reduces idle CPU, network requests, disk writes, and duplicate-process conflicts without delaying active combat contacts. State polling now carries the last Sam.py revision, idles at a slower cadence outside combat, backs off during outages, and coalesces pending sync work. The interface and runtime snapshot update only when their authoritative values change.

Only one Desktop instance may run per Windows user session. A second launch displays a notice and exits instead of opening another Sam.py poller or failing the OSC UDP bind.

## Interface

The normal interface contains six focused pages:

- **Dashboard** — linked character, HP, MP, effective combat profile, statuses, Dungeon Master gate, and filtered recent activity.
- **Actions** — searchable recovery, Magicks, Technicks, favorites, costs, and availability reasons.
- **NPC Mode** — searchable enemy roster, favorites, verified attacker selection, and hit diagnostics.
- **Connection** — Sam.py pairing and VRChat OSC listener state.
- **Diagnostics** — contract checks, reconnect controls, copied summaries, and sanitized support bundles.
- **Settings** — ports, compatibility damage, avatar bridge behavior, UI scaling, accessibility, and update settings.

Debugging and manual-test pages are not part of the normal interface.

## One-click startup

Double-click:

```text
Start Stories OSC.bat
```

The launcher creates a private `.venv`, installs or updates only the required components, and starts the application. Future launches skip installation unless `requirements.txt` changed.

The source package requires Python 3.11 or newer. The included GitHub workflow builds a standalone Windows release that does not require players to install Python separately.

## Sam.py pairing

1. Run `/osc_link` in Discord.
2. Enter the one-use code and select **Pair Device**.

## Recovery

Recovery values are calculated by Sam.py, not trusted from the desktop client. The VPS checks:

- Current HP and MP
- Effective HP/MP ceilings from equipment and augments
- Inventory quantities
- Item definitions
- Potion, Ether, and revival lores
- Compatible equipped potency effects
- Owned licenses and required scrolls
- Healing-magick formulas and Channeling-adjusted MP costs

Items are consumed and magick MP is spent only after server validation succeeds.

## Dungeon Master gate

Every action originating from a VRChat Contact requires RP Combat to be enabled and an active Dungeon Master session in the Admin Panel. This includes incoming damage, Contact spells (including healing), Technicks, Items, and newly applied harmful statuses. Typical rejections include:

```text
RP Combat Disabled - Spell Trigger Ignored
No Active DM's - Item Trigger Ignored
No Active DM's - No Hit Registered
```

Only VRChat-triggered actions use this gate. Pairing, state pulls, Discord combat, Player/Admin Panel actions, Desktop Recovery, and ordinary Sam.py commands continue through their normal authoritative paths.

## Authoritative dynamic damage

Incoming VRChat damage is resolved by Sam.py instead of fixed Desktop values. The target's effective maximum HP and final Base + Gear + Augment DEF, RES, EVA, and VIT affect the result. Friendly-to-Friendly harmful Contacts are rejected before Sam.py HP or statuses change. `1000 Needles` remains fixed at exactly 1,000 damage.


## v0.8.9 status authority and KO safety

Desktop v0.8.9 keeps Sam.py authoritative for real-time status timing and damage-over-time processing.

- Dead characters cannot send local Spell or Technick actions.
- Critical HP uses living HP below 15%.
- Sam.py status snapshots replace stale Desktop status timers atomically.
- Bleed, Burn, Silence, Freeze, and Bind are mirrored from Sam.py rather than ticked twice locally.
- Sam.py status tick, expiration, and KO events appear once in Recent Activity.
- Requires OSC API v0.8.9 for the complete status lifecycle.


## Updates

GitHub update support is ready but requires the repository's `owner/repository` value in **Settings**. Every download and installation requires confirmation.

## Unity tool

Unity Contact Tool v0.5.8 TB6.2 is recommended for the current KO-safe, weapon-attachment, Attack, Spell, Technick, Item, and Debuff workflow. Avatars generated by v0.5.1 or v0.5.2 should run the Unity tool's spell-contact repair before testing spell hits.


## v0.8.0 Unity synchronization
Supports `SoY_SpellType`, Enemy Mode, Mist Charge, Curse of Diablos warnings, healing rejection, and one-second hit protection through the current Sam.py OSC API.


## v0.8.1 binary spell Contact bus

Unity Tool v0.5.3 no longer depends on Constant Contact Receivers writing arbitrary Int values. It sends spell IDs through nine unsynced Bool parameters:

```text
SoY_SpellActive
SoY_SpellBit0
SoY_SpellBit1
SoY_SpellBit2
SoY_SpellBit3
SoY_SpellBit4
SoY_SpellBit5
SoY_SpellBit6
SoY_SpellBit7
```

The Desktop waits 30 milliseconds for the OSC packets to settle, reconstructs the ID, and submits the normal `spell_type` integer to Sam.py. Direct `SoY_SpellType` input remains supported.

Example: Curaja is ID `4`, encoded as `00000100`, so only `SoY_SpellBit2` is active.


## v0.8.5 VRChat action gate, Technicks, and Items

All actions decoded from avatar Contacts are marked `vrc_trigger: true`. Sam.py accepts them only when both RP Combat and the Dungeon Master gate are active. This applies to healing and damage equally. The restriction does not affect Discord, Player Panel, Admin Panel, Desktop Recovery, or normal Sam.py command paths.

Technicks and Items use the same compact binary design as spells:

```text
SoY_TechnickActive + SoY_TechnickBit0-7
SoY_ItemActive      + SoY_ItemBit0-7
```

The Desktop reconstructs IDs from `TECHNICK_ID_REGISTRY_v1.json` and `ITEM_ID_REGISTRY_v1.json`. Direct local Item use is never trusted as inventory proof: OSC API v0.8.4 delegates the action to the current Sam.py `fight_system.py`, which verifies the linked character owns the item, confirms it is usable, applies the current encounter target rules, and consumes one item only after a valid use. Direct local Technick use requires both the owned Technick license and the matching `Technick: <Name>` teaching item before calling the canonical Technick resolver. Incoming Item/Technick Contact buses identify what reached the avatar but do not consume the target's inventory or make the target execute the action.

## v0.8.2 Curse Of Diablos display repair

The Overview page now shows a Curse Of Diablos bar only when Sam.py reports that the active character has the curse. The desktop converts the authoritative 0-100 value to the normalized 0-1 Float required by the avatar radial gauge and rejects malformed telemetry before sending it to VRChat.


## v0.8.3 incoming restorative spell contacts

Decoded spell contacts are now submitted immediately to Sam.py. OSC API v0.8.2 applies healing, revival, and supported cleanse effects to the linked target character and returns the updated HP state to the Desktop.


## NPC Mode

In Settings, enable **NPC Mode**, refresh the rosters, and select an enemy. The linked Desktop uses a device-local runtime copy of that enemy's HP, MP, level, combat stats, affinities, regions, spells, Technicks, and items. The static Sam.py enemy roster is never modified.

For Player → NPC Contacts, choose a verified attacker. Desktop sends only the Discord user ID and character name. Sam.py rejects missing, ambiguous, deleted, or KO attackers and recalculates all combat stats server-side. Weak, Average, Strong, and Critical remain Contact tiers; NPC maximum HP is not attack power.


## Automatic updates

The Desktop checks the configured GitHub Releases repository automatically when it starts and every six hours. An available update changes the top-right button to **Install update**. Download and installation progress remain visible, and installer details are written to `%APPDATA%/StoriesOfYggdrasil/OSCContactSystem/update_install.log`.

## Standalone VRC actions

VRC Item, Spell, and Technick actions do not require a Sam.py encounter. Items used without an encounter apply to the linked character, while offensive Spell/Technick effects resolve on whichever avatar receives the matching incoming Contact. RP Combat and Dungeon Master gating still apply because these are VRChat-triggered actions.
