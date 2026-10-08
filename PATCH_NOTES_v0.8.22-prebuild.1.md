# Stories Of Yggdrasil OSC v0.8.22-prebuild.1

## Protocol 21 — Physical Helpful Items

This Test Build adds the Desktop half of TB18 physical item interactions.

- Potion-style helpful items are armed by `SoY_ItemType` without consuming inventory.
- Self Head contact submits an authenticated self-use request.
- Other-player Head contact submits an authenticated actor attempt.
- The recipient's TB18 Head receiver submits the matching authenticated receipt.
- Sam.py may commit the transaction only when exactly one valid matching attempt exists in the short match window.
- Ambiguous or expired interactions fail closed and consume nothing.
- Helpful physical IDs ignore the legacy generic incoming Item bus so effects cannot double-apply.
- `SoY_ItemUseResult` and `SoY_ItemReceiveResult` return server result codes to the avatar for success/failure presentation.

## Automatic Player-to-Player attribution

- TB18 Attack volumes report local Weak/Average/Strong/Critical attacker-side touch attempts.
- A canonical Player-side hit on the target submits an authenticated target receipt.
- Sam.py pairs exactly one attacker attempt with exactly one target receipt inside the short identity window.
- Actor stats are resolved against target defenses, armor, augments, and the normal DM gate by Sam.py.
- Ambiguous simultaneous attackers fail closed instead of guessing.
- Protocol 20 retains the existing manual/verified PvP Source fallback.

## Compatibility

- Protocol 20 / TB17.5 remains supported for existing avatars.
- Protocol 21 physical helpful items require Unity Tool TB18.
- Recommended restricted OSC API: 0.8.19.
- Stable v0.8.21 remains untouched.

## Server requirement

The Sam.py v1.9.33 / Fight System v4.4.219 patch adds the authoritative Protocol 21 transaction broker and upgrades the restricted OSC API to v0.8.19. End-to-end testing requires these authenticated routes:

- `/helpful-item/self`
- `/helpful-item/attempt`
- `/helpful-item/receipt`
- `/pvp/attempt`
- `/pvp/receipt`
