# Stories Of Yggdrasil OSC v0.7.0

A streamlined Windows desktop bridge between VRChat OSC and the VPS-hosted Sam.py system.

## Interface

The normal interface contains four focused pages:

- **Overview** — linked character, HP, MP, RP Combat, statuses, Dungeon Master gate, and recent activity.
- **Recovery** — usable potions, ethers, revival items, and restorative magick.
- **Connection** — Sam.py pairing and VRChat OSC listener state.
- **Settings** — ports, damage values, avatar bridge behavior, and GitHub update settings.

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

Incoming damage and newly applied harmful statuses require RP Combat to be enabled and an active Dungeon Master session in the Admin Panel. Rejected hits display:

```text
No Active DM's - No Hit Registered
```

Healing, MP recovery, pairing, state pulls, and status removal remain available while the damage gate is closed.

## Updates

GitHub update support is ready but requires the repository's `owner/repository` value in **Settings**. Every download and installation requires confirmation.

## Unity tool

Unity Contact System v0.4.4 is included in the complete bundle. Existing v0.4.3-installed avatar contacts remain compatible; replacing the Editor script does not require rebuilding the avatar unless the installer reports a missing hook.


## v0.8.0 Unity synchronization
Supports `SoY_SpellType`, Enemy Mode, Mist Charge, Curse of Diablos warnings, healing rejection, and one-second hit protection through Sam.py OSC API v0.8.0.
