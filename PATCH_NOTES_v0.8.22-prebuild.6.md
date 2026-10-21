# v0.8.22-prebuild.6 — Contact path diagnostics & color-coded activity

- Recent Activity highlights registered damage, restoration, held contacts, and errors using distinct readable foreground colors. Filtering, grouping, searching and saved logs remain unchanged.
- When an incoming Player Contact cannot enter Protocol 21, show the sanitized Contact path and marker version in the hold entry, so an external alias/Protocol 20 receiver is not confused with a server-matching failure.
- Deliberately does NOT bypass failed identity validation or automatically attribute any external hits to an arbitrary player.
- Continuing investigation: scrolls are learned/consumed by the current economy design but the older OSC bridge still checks the inventory for Scroll: Name; spell 146 (Radiant Fracture) needs synchronization on VPS; MP regeneration is server-owned; Write Defaults and menu editor changes belong to a separate tested Unity Tool patch.
- Stable v0.8.21 remains unchanged.
