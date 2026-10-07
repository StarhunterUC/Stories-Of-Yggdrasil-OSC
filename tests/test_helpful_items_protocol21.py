from __future__ import annotations

import copy

from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.config import DEFAULT_CONFIG
from stories_yggdrasil_osc.controller import BridgeController
from stories_yggdrasil_osc.helpful_items import (
    HELPFUL_ITEM_ID_TO_NAME,
    is_physical_helpful_item,
)


def _controller():
    config = copy.deepcopy(DEFAULT_CONFIG)
    events = []
    state = CombatState(
        maximum_hp=1000,
        current_hp=1000,
        damage_values=config["combat"]["damage"],
        invulnerability_seconds=0,
        critical_hp_percent=0.15,
        status_rules=config["statuses"],
        clear_statuses_when_disabled=True,
        combat_enabled=True,
    )
    controller = BridgeController(
        config=config,
        state=state,
        send_parameter=lambda _name, _value: None,
        pulse_parameter=lambda _name, _duration: None,
        event_sink=events.append,
    )
    return controller, events


def test_registry_keeps_harmful_ids_out():
    assert is_physical_helpful_item(1)
    assert HELPFUL_ITEM_ID_TO_NAME[1] == "Potion"
    assert not is_physical_helpful_item(23)  # Aero Mote
    assert not is_physical_helpful_item(26)  # Bacchus's Wine
    assert not is_physical_helpful_item(33)  # Dark Energy


def test_self_head_touch_uses_selected_helpful_item():
    controller, events = _controller()
    controller.handle_osc("/avatar/parameters/SoY_ItemType", (1,), 1.00)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemSelfTouch", (True,), 1.10)

    matches = [event for event in events if event.event == "helpful_item_touch"]
    assert len(matches) == 1
    assert matches[0].metadata["scope"] == "self"
    assert matches[0].metadata["item_id"] == 1


def test_other_head_touch_uses_selected_helpful_item():
    controller, events = _controller()
    controller.handle_osc("/avatar/parameters/SoY_ItemType", (4,), 2.00)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemOtherTouch", (True,), 2.10)

    matches = [event for event in events if event.event == "helpful_item_touch"]
    assert len(matches) == 1
    assert matches[0].metadata["scope"] == "other"
    assert matches[0].metadata["item_id"] == 4


def test_other_head_touch_is_rising_edge_only():
    controller, events = _controller()
    controller.handle_osc("/avatar/parameters/SoY_ItemType", (1,), 3.00)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemOtherTouch", (True,), 3.10)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemOtherTouch", (True,), 3.11)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemOtherTouch", (False,), 3.20)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemOtherTouch", (True,), 3.30)

    matches = [event for event in events if event.event == "helpful_item_touch"]
    assert len(matches) == 2


def test_head_receiver_bus_reconstructs_item_id():
    controller, events = _controller()
    # 5 = 0b00000101
    controller.handle_osc("/avatar/parameters/SoY_HelpItemBit0", (True,), 4.00)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemBit2", (True,), 4.01)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemActive", (True,), 4.02)
    controller.tick(4.06)

    assert controller.telemetry["helpful_item_received_type"] == 5
    matches = [event for event in events if event.event == "helpful_item_received"]
    assert len(matches) == 1
    assert matches[0].metadata["item_id"] == 5


def test_head_receiver_bus_clears_on_exit():
    controller, _events = _controller()
    controller.handle_osc("/avatar/parameters/SoY_HelpItemBit0", (True,), 5.00)
    controller.handle_osc("/avatar/parameters/SoY_HelpItemActive", (True,), 5.01)
    controller.tick(5.05)
    assert controller.telemetry["helpful_item_received_type"] == 1
    controller.handle_osc("/avatar/parameters/SoY_HelpItemActive", (False,), 5.10)
    assert controller.telemetry["helpful_item_received_type"] == 0


def test_tb18_protocol21_beacon_recovers_late_start():
    from stories_yggdrasil_osc.avatar_compatibility import UnityAvatarCompatibility

    tracker = UnityAvatarCompatibility()
    tracker.note_protected_input()
    assert not tracker.compatible
    assert tracker.observe_parameter("SoY_UnityMarkerBeacon", 121)
    assert tracker.compatible
    assert tracker.protocol == 21
    assert tracker.tool_version == "v0.5.10 TB18"
    assert tracker.observe_parameter("SoY_UnityMarkerBeacon", 122)
    assert tracker.compatible
