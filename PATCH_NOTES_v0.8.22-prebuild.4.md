# v0.8.22-prebuild.4 — PvP handshake stability

This Desktop pre-build continues the Protocol 21 / Unity TB18.x line without touching v0.8.21 stable.

- One physical sword swing may trigger multiple local Contact edges; suppress repeat **same-tier** attempts within 0.85 seconds, without hiding distinct-tier wiring problems.
- PvP outgoing attempts are held during NPC runtime selection and until Sam.py confirms the Player runtime.
- Repair the prebuild.3 `remote_state` fixture AttributeError so the complete regression suite can run again.
- Deploy the corresponding separate VPS handshake reliability module with preflight/backups; it is NOT included in the Windows installer.
- Require a controlled two-player test and confirm no unmatched or ambiguous contact damages the wrong player.
- No combat damage formula modification; Aurora→Alice minimum 1-damage hits should be reviewed with effective ATK/DEF before balancing.
