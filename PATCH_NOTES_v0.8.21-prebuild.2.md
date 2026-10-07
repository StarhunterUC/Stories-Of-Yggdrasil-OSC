# Stories Of Yggdrasil OSC Desktop v0.8.21-prebuild.2

Protocol 20 test client paired with Unity Tool v0.5.10 TB17.

## Fixes

- Requires the TB17 / Protocol 20 Unity marker for direct Stories-generated gameplay input.
- Protocol 19 avatars fail closed and report **Avatar Update Required** until repaired/migrated in the Unity Tool.
- Adds `SoY_ExternalDamageSource` support.
- Canonical `SoY_DamageSourceEnemy` is now treated only as Stories Enemy/NPC alignment.
- External `Sword`, `Weapon`, and `Hands` compatibility can no longer poison canonical Stories Friendly/Enemy classification.
- A direct SoY hit carrying `SoY_ExternalDamageSource` is treated as external/unknown for attribution rather than as canonical Friendly.
- High-frequency Damage/Healing/External source telemetry is suppressed from Recent Activity while remaining available to diagnostics/runtime logic.
- Retains the prebuild.1 catalog-spam fix and explicit NPC Mode enable/disable workflow.
- Diagnostics now report Unity Tool version, protocol, schema validity, and compatibility state.

## Required pair

- Unity Tool: v0.5.10 TB17
- Unity Protocol: 20
- Sam.py OSC API: 0.8.18

Sam.py is unchanged by this test build.
