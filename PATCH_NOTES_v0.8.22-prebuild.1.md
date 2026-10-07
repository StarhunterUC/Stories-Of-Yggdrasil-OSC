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

## Compatibility

- Protocol 20 / TB17.5 remains supported for existing avatars.
- Protocol 21 physical helpful items require Unity Tool TB18.
- Recommended restricted OSC API: 0.8.19.
- Stable v0.8.21 remains untouched.

## Server requirement

The uploaded Sam.py/fight_system.py patch adds the authoritative item transaction helper. The restricted OSC API service must expose the three Protocol 21 handlers used by this Desktop build before end-to-end testing:
`/helpful-item/self`, `/helpful-item/attempt`, and `/helpful-item/receipt`.
