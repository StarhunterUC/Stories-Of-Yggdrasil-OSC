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
