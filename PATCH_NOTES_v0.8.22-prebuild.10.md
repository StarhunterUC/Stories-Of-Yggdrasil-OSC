# v0.8.22-prebuild.10 — Spell Registry and Caster Payment Diagnostics

Registry: Unity TB18.2's seven Light Magicks IDs 145–151 appended to the Desktop's existing 144-spell mapping (including legacy Chakra Heal 98 and Aura Shielding 99).

Local casting (`spell_cast_type`) is charged by the existing Sam.py `fight_system.py` payer. Incoming spell Contacts (`spell_type`) do not charge the recipient. The Desktop displays actual MP/Gil paid from the server response instead of client-side cost guesses.

This update alone does **not** fix missing spells on the VPS. It does not invent specialized Light Imbuement support effects, nor does it change damage calculations, scroll learning, or MP regeneration.
