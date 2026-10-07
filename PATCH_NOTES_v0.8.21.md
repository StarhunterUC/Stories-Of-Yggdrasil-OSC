# Stories Of Yggdrasil OSC Desktop v0.8.21

Protocol 20 / TB17 public Desktop release.

## Protocol 20 compatibility

- Promotes the tested v0.8.21-prebuild.4 Desktop line to Stable.
- Supports the periodic `SoY_UnityMarkerBeacon` heartbeat (117/118), allowing the Desktop to recover the Unity Tool / Protocol / schema identity when the Desktop starts after the avatar.
- Retains fail-closed validation for incomplete, invalid, or unknown marker data.
- Retains Protocol 20 separation between canonical `SoY_DamageSourceEnemy` and outside `SoY_ExternalDamageSource` compatibility.
- Recommended Unity authoring pair is now **Unity Tool v0.5.10 TB17.5 / Protocol 20**.

## Update channels

- Adds **Stable** and **Test Builds** update channels under Settings → Updates.
- Stable continues to use public GitHub releases only.
- Test Builds can see GitHub prereleases, including future `0.8.22-prebuild.x` releases.
- Version ordering explicitly treats a prebuild as older than the final release of the same version:
  `0.8.21-prebuild.4 < 0.8.21 < 0.8.22-prebuild.1`.
- Update downloads remain checksum-verified before installation.

## Existing systems retained

- Sam.py remains authoritative for combat, HP/MP, statuses, recovery, NPC damage, PvP attribution, and DM gating.
- Windows Sam.py HTTPS continues through WinHTTP / Schannel.
- NPC Mode, verified Player → NPC identity, late-start avatar detection, and activity-log cleanup remain intact.

## Required pair

- Desktop: **v0.8.21**
- Unity Tool: **v0.5.10 TB17.5**
- Unity Protocol: **20**
- Sam.py OSC API: **0.8.18 recommended / 0.8.13 minimum**

Sam.py is unchanged.
