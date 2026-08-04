# Quick Start — Desktop v0.8.14

1. Run `Start Stories OSC.bat`.
2. Pair the Desktop with Sam.py using `/osc_link`.
3. Confirm the Connection page reports OSC API v0.8.13 or newer.
4. Publish the avatar after Unity Tool v0.5.8 TB6.2 has installed or repaired the current Contacts.
5. Enable RP Combat and open the Dungeon Master gate before testing VRChat-triggered actions.

## Verified Player → NPC damage

1. Open **Settings → NPC Mode**.
2. Select **Refresh Rosters** and choose the NPC.
3. Select **Verified stats**.
4. Choose the attacking player and character. On API v0.8.13, enter the numeric Discord ID and exact character name manually. API v0.8.14 populates both selectors.
5. Save Settings.
6. Strike the NPC avatar with Weak, Average, Strong, or Critical Contacts.
7. Review **Last hit diagnostics** for attacker ATK/MAG/SPD, NPC DEF/RES, mitigation, model, and final damage.

Use **Compatibility fallback** only for transition testing. It does not use a real player character's stats.

## Windows release build

Run:

```powershell
powershell -ExecutionPolicy Bypass -File ".\BUILD_AND_PACKAGE_v0.8.14.ps1"
```

The script prepares the environment, runs tests and the source audit, builds the Windows executable, creates the release ZIP, and writes its SHA-256 checksum.


## QOL shortcuts

- Use **Reconnect All** in the global header after changing worlds or reconnecting VRChat.
- Favorite common Actions to place them in Quick Actions.
- Pause Recent Activity to inspect entries without stopping collection.
- Use **Diagnostics → Create Support Bundle** before reporting an issue. The bundle redacts tokens and Discord IDs.
