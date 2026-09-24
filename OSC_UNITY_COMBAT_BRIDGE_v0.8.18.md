# SoY Unity / World Combat Bridge Contract — Desktop v0.8.18

This document defines the optional attribution signals understood by the Desktop after the v0.8.18 combat-authority patch.

## Authority split

- **Avatar / Unity Contacts:** report that a Contact occurred and its coarse tier/type.
- **Desktop:** forwards only identity/context it can prove or that comes from a trusted local bridge.
- **Sam.py:** resolves combat profiles, validates NPC bindings/player identity, applies the DM gate, and calculates final damage/healing.

Do not add a client-authored final damage or arbitrary `power` field to Player Contact events.

## Existing Contact inputs remain supported

The current SoY hit tier and source-alignment Contacts remain valid. Desktop v0.8.18 continues to decode Weak / Average / Strong / Critical through the existing controller and uses the existing Enemy alignment pulse when available.

## Optional trusted-local source hint inputs

A future Unity/world companion or other trusted process on the same machine may send these OSC addresses immediately before the related hit Contact:

```text
/soy/combat/source/kind            "npc" | "player"
/soy/combat/source/avatar_id       "avtr_..."
/soy/combat/source/vrchat_user_id  "usr_..."
/soy/combat/source/enemy_name      "Enemy Template Name"
/soy/combat/action/name            "Server-authored NPC action name"
/soy/combat/action/kind            "physical" | "magick" | "healing"
/soy/combat/action/element         "Fire" | "Ice" | ...
/soy/combat/source/clear           1
```

Hints are intentionally short-lived (default 2 seconds) and consumed by the next routed incoming hit. They are context only: Sam.py still validates identities/actions and remains authoritative.

## NPC -> Player

Preferred flow:

1. Identify the NPC Avatar ID from a trusted bridge or choose a mapped source in Desktop.
2. Emit/retain the normal hit tier Contact.
3. Desktop submits a defender-reported combat event targeting its own linked Player.
4. Sam.py verifies that Avatar ID is bound to exactly the intended `enemies.json` profile and resolves the hit.

If the damaging model is unclassified, Desktop can default the *kind* to Enemy, but it still holds the hit until a specific mapped NPC can be identified. This prevents a random/unmapped avatar from borrowing another NPC's combat stats.

## Player -> Player

Preferred flow:

1. Supply a verified remote `vrchat_user_id` through a trusted bridge, or explicitly select a live verified Player identity published by Sam.py.
2. Emit the normal hit tier Contact.
3. The defender's Desktop reports the event to Sam.py.
4. Sam.py verifies that the source identity maps to the linked Player and rejects ambiguous Avatar-ID-only mappings.

A raw Contact pulse by itself must not be used to guess which Player attacked.

## Player -> NPC

The new Sam.py combat endpoint is attacker-reported for this direction. The current Desktop NPC Mode is target-reported and therefore remains on its existing verified-attacker path in v0.8.18.

For a later automatic outgoing bridge, the attacking Player's Desktop/world companion must know:

- that its local Player caused the Contact;
- which NPC Avatar/profile was struck;
- the Contact tier/action context.

Once that is reliable, it can submit Player -> NPC directly through `/api/osc/combat/event`. Until then, do not remove the existing NPC Mode path.

## Friendly / enemy behavior

If a model has no explicit Friendly/Enemy signal and a damaging Contact is received:

- when a verified PvP source is selected/hinted, treat it as Player/PvP;
- otherwise Desktop may default it to Enemy;
- an Enemy default is **not** permission to invent an NPC identity. A mapped NPC source is still required for the v0.8.18 endpoint.

## Security boundary

`/soy/combat/*` is a local companion hook, not a new server trust boundary. Do not expose the Desktop OSC listener to untrusted remote networks. Sam.py must continue validating every submitted identity and action.
