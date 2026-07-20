# OSC Contracts

- `OSC_CONTRACT_v6.json` — legacy/direct compatibility contract.
- `OSC_CONTRACT_v8.json` — Unity v0.5.2 direct spell-ID contract.
- `OSC_CONTRACT_v9.json` — Unity v0.5.3 binary spell Contact bus.
- `SPELL_ID_REGISTRY_v2.json` — stable spell IDs used by Desktop and Sam.py.

Desktop v0.8.3 accepts both the direct `SoY_SpellType` Int and the v0.5.3 `SoY_SpellActive` + `SoY_SpellBit0-7` bus.

Desktop v0.8.3 sends `SoY_DiablosPercent` as a normalized Float (`0.0` to `1.0`) while the VPS continues storing the authoritative percentage as `0` to `100`.

- `OSC_CONTRACT_v11.json` — separates local cast/use Int parameters from incoming binary Contact buses, adds caster-side MP payment, and preserves target-side inventory/MP.
- `TECHNICK_ID_REGISTRY_v1.json` — stable current Technick IDs generated from the live Sam.py license catalog.
- `ITEM_ID_REGISTRY_v1.json` — stable current combat-item IDs generated from the live Sam.py item catalog.

Desktop v0.8.4 marks only Contact-originated actions as `vrc_trigger`. OSC API v0.8.3 applies RP Combat and Dungeon Master gating to those events while leaving non-VRChat Sam.py paths unchanged.

Desktop v0.8.5 sends direct `SoY_SpellType`, `SoY_TechnickType`, and `SoY_ItemType` values as local cast/use events. Binary buses remain incoming target-side events. OSC API v0.8.4 charges MP only to the local caster, validates `Technick: <Name>` separately from magick `Scroll: <Name>`, and never consumes target inventory for an incoming Contact.
