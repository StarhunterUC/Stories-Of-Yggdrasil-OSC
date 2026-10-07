# Stories Of Yggdrasil OSC Desktop v0.8.21-prebuild.4

TB17.1 late-start compatibility beacon support.

## Fixes

- Accepts the TB17.1 encoded local compatibility beacon (`SoY_UnityMarkerBeacon` values 117/118).
- Desktop can now recover the full Tool/Protocol/schema identity even if it starts after VRChat already emitted the static Unity marker parameters.
- Unknown beacon values do not bypass fail-closed validation.
- Retains Protocol 20 external-source separation, NPC Mode fixes, marker startup-race handling, and activity-log cleanup.

## Required pair

- Unity Tool: v0.5.10 TB17.1
- Unity Protocol: 20
- Sam.py OSC API: 0.8.18

Sam.py is unchanged.
