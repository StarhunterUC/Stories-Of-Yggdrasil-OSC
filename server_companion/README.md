# Optional OSC API v0.8.14 companion

Desktop v0.8.11 works with OSC API v0.8.13 by allowing manual Discord ID and character-name entry.

Deploying this companion patch upgrades the current v0.8.13 Admin API to v0.8.14 and adds a read-only attacker roster to the existing authenticated `/api/osc/npc/catalog` response. This enables the Desktop player and character dropdowns.

The patch:

- modifies only the current `/opt/sam/admin_server.py`;
- creates a timestamped backup;
- ignores nonnumeric metadata records such as `dump`;
- marks KO characters ineligible;
- returns current stat previews for display only;
- never trusts Desktop-provided stats for damage;
- compiles before restarting `sam.service`;
- restores the backup if deployment fails.

Run from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File ".\UPLOAD_AND_DEPLOY.ps1"
```

The live v0.8.13 Player → NPC damage verifier should pass before applying this catalog-only companion.
