# v0.8.22-prebuild.13 — Authoritative Status/Ability UI Compatibility

- Display Sam.py-provided `notes` for Magicks and Technicks in the Actions catalog when present. Does not invent descriptions missing from the VPS registry.
- Read `status_effects` supplied as a keyed object or a list; maintain authoritative character status isolation.
- Suppress duplicate local i-frame IGNORED Contact diagnostics within one second while preserving combat holds, registered damage, heals and errors.
- Regression tests for each change.

**No authoritative VPS changes are included.** NulAll Guard semantics, legacy combat audit writes, canonical spell registry descriptions, NPC HP authority, and PvP damage identity still require separate verified VPS changes.
