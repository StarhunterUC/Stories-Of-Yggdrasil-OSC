# Quick Start — Desktop v0.8.18

1. Run `Start Stories OSC.bat`.
2. Pair the Desktop with Sam.py using `/osc_link`.
3. Confirm the Connection page reports OSC API v0.8.13 or newer. **v0.8.18 is recommended and is required for the new combat-authority route.**
4. Publish the avatar after the current Unity Tool has installed/repaired the SoY Contacts.
5. Enable RP Combat and open the Dungeon Master gate before testing VRChat-triggered damage.
6. Open **NPC Mode**, select **Refresh Rosters**, and verify the new **Incoming Contact Attribution** section loads mapped NPC and verified Player sources.

## Incoming NPC → Player damage

1. Bind the NPC Avatar ID to its enemy template in Admin → OSC → NPC Avatar Bindings.
2. In Desktop → NPC Mode → Incoming Contact Attribution, choose the mapped **NPC → Player source**.
3. Leave Desktop NPC Mode itself disabled when your linked character is the Player target.
4. Trigger a Weak / Average / Strong / Critical damaging Contact.
5. The Desktop sends an idempotent `/combat/event`; Sam.py validates the NPC identity and calculates the result from `enemies.json` vs the Player's effective Fight System stats.

If a model is unclassified, the Desktop can default it to Enemy, but it will not invent an enemy profile. A mapped NPC source or fresh trusted identity hint is still required.

## Player → Player damage

1. Refresh the combat identity roster.
2. Choose the verified remote Player under **Player → Player source**, or provide a short-lived trusted-local `/soy/combat/source/...` identity hint.
3. Trigger the normal Contact.
4. The defender's Desktop reports the hit; Sam.py verifies the remote identity and writes the defender's HP authoritatively.

The Desktop deliberately holds unattributed PvP rather than guessing a Player from a generic Contact.

## Verified Player → NPC damage

The current NPC Mode route is preserved in v0.8.18 because the new combat endpoint expects Player → NPC to be attacker-reported. Continue using the existing verified attacker workflow:

1. Enable **NPC Mode** and choose the NPC.
2. Select **Verified stats**.
3. Choose the attacking Player and character.
4. Strike the NPC avatar with the existing hit-tier Contacts.
5. Review **Last hit diagnostics** for the server-returned calculation.

See `OSC_UNITY_COMBAT_BRIDGE_v0.8.18.md` for the follow-up contract needed to automate outgoing Player → NPC identity later.

## Windows release build

Run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\BUILD_AND_PACKAGE_v0.8.18.ps1
```

The script prepares the environment, runs tests and the source audit, builds the Windows executable, creates the release ZIP, and writes its SHA-256 checksum.

## QOL shortcuts

- **Reconnect All** remains a manual recovery control; ordinary Sam.py edits and service restarts should resynchronize automatically.
- Favorite common Actions to place them in Quick Actions.
- Pause Recent Activity to inspect entries without stopping collection.
- Use **Diagnostics → Create Support Bundle** before reporting an issue. The bundle redacts tokens and Discord IDs.
