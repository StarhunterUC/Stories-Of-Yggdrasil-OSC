# Stories Of Yggdrasil OSC Desktop v0.8.21-prebuild.3

Protocol 20 marker-handshake hotfix for TB17 testing.

## Fixes

- Fixes the contradictory **"protocol 20 is unsupported; protocol 20 is required"** message.
- VRChat may emit the local Bool marker default (`SoY_UnityToolPresent = false`) before the Unity marker state driver publishes the rest of the marker. Desktop no longer treats that single startup edge as proof that the avatar is outdated.
- A complete TB17+ marker with Protocol 20 and `SoY_UnitySchemaValid = true` is accepted even if the Present Bool briefly arrived false first.
- Protocol 20 with an incomplete marker now reports **marker incomplete / run Safe Repair All or Migrate & Validate**, instead of incorrectly calling Protocol 20 unsupported.
- Protocol 19 still fails closed.
- Invalid schema still fails closed.
- Future protocols still require a Desktop update.
- Retains Protocol 20 external-source separation, NPC Mode fixes, and activity-log cleanup from prebuild.2.

## Required pair

- Unity Tool: v0.5.10 TB17 or newer
- Unity Protocol: 20
- Sam.py OSC API: 0.8.18

Sam.py is unchanged.
