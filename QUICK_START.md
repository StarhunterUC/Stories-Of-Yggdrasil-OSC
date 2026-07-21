# Quick Start — Desktop v0.8.7

1. Install or update Unity Contact Tool v0.5.4.
2. In Unity, run **Incoming Contacts → REPAIR v0.5.1 / v0.5.2 SPELL CONTACTS** on avatars created by older tool versions.
3. Publish the avatar so VRChat regenerates its OSC parameter configuration.
4. Start `Start Stories OSC.bat`.
5. Pair with Sam.py and enable RP Combat.
6. Test Cure ID `1` and Curaja ID `4`; Recent Activity should show different resolved spell IDs.

## Technick and Item Contacts

Create the outgoing sender in Unity Tool v0.5.4, install the corresponding incoming binary bus on the target avatar, and keep the Desktop application linked to Sam.py. Both RP Combat and Dungeon Master Mode must be active. Item Contacts use the linked character's current Sam.py inventory and current encounter target; missing or unusable items are rejected without consumption.


## NPC Mode

Open **Settings → NPC Mode**, select **Refresh Roster**, choose an enemy, enable NPC Mode, and save. Enemy Mode is forced on while the NPC profile is active. Disabling NPC Mode returns the Desktop to the linked Sam.py player character without changing the static enemy roster.
