# v0.8.22-prebuild.11 — Dynamic Active Effects and NPC Profile Clarity

- Active Status on Desktop now renders all named effects supplied by the current authoritative Sam.py character, rather than five hardcoded status tiles.
- Displays remaining time, stacks and potency when supplied by the server, with no locally invented expiration authority.
- Prevents stale local Player statuses from leaking into a linked NPC's displayed effects.
- Distinguishes absent stats from literal zero and warns when NPC effective stats are zero while the NPC roster provides nonzero reference stats. Roster values are marked display reference only; no combat formula or authoritative stats are overwritten.
- Accepts local dictionary-key views in offline status display (regression fix).

No damage formulas, NulAll Guard behavior, PvP identity gates, server records, or Protocol 20/21 support are changed in this client update.

## Verification

Automated Windows pre-build tests, source audit and executable packaging must pass before a ZIP is published.
