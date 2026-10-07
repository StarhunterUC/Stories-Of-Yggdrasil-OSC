from __future__ import annotations

# Protocol 21 physical helpful-item registry.
# These IDs must remain aligned with Unity Tool TB18 and Sam.py/fight_system.py.
HELPFUL_ITEM_ID_TO_NAME: dict[int, str] = {
    1: "Potion",
    2: "Hi-Potion",
    3: "X-Potion",
    4: "Ether",
    5: "Hi-Ether",
    6: "Elixir",
    8: "Phoenix Down",
    10: "Rainbow Phoenix Feather",
    11: "Antidote",
    12: "Eye Drops",
    13: "Echo Herbs",
    14: "Gold Needle",
    15: "Prince's Kiss",
    16: "Chronos Tear",
    17: "Handkerchief",
    18: "Remedy",
    19: "Vaccine",
    20: "Serum",
    21: "Diablos Stabilizer",
    28: "Baltoro Seed",
    30: "Blue Herb",
    31: "Bubble Mote",
    37: "Domaine Calvados",
    40: "Green Herb",
    43: "Hypo Spray",
    50: "Nu Khai Sand",
}

HELPFUL_ITEM_IDS = frozenset(HELPFUL_ITEM_ID_TO_NAME)

ITEM_RESULT_IDLE = 0
ITEM_RESULT_SUCCESS = 1
ITEM_RESULT_NO_ITEM = 2
ITEM_RESULT_INVALID_TARGET = 3
ITEM_RESULT_NO_EFFECT = 4
ITEM_RESULT_BLOCKED = 5
ITEM_RESULT_EXPIRED = 6


def helpful_item_name(item_id: int) -> str:
    try:
        return HELPFUL_ITEM_ID_TO_NAME.get(int(item_id), "")
    except (TypeError, ValueError):
        return ""


def is_physical_helpful_item(item_id: int) -> bool:
    try:
        return int(item_id) in HELPFUL_ITEM_IDS
    except (TypeError, ValueError):
        return False
