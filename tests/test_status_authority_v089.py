from __future__ import annotations

import time

from stories_yggdrasil_osc.combat import CombatState
from stories_yggdrasil_osc.controller import BridgeController


def make_state(hp: int = 1000) -> CombatState:
    return CombatState(
        maximum_hp=1000,
        current_hp=hp,
        damage_values={"weak": 40, "average": 100, "strong": 200, "critical": 400},
        invulnerability_seconds=1.0,
        critical_hp_percent=0.15,
        status_rules={"bleed": {"duration_seconds": 12, "tick_seconds": 2, "damage": 15}},
        combat_enabled=True,
    )


def make_controller(state: CombatState, events: list, sent: list) -> BridgeController:
    config = {
        "sam": {"enabled": True, "token": "token", "authoritative_vrc_damage": True},
        "combat": {"block": {"enabled": True, "window_seconds": 0.18, "hit_settle_seconds": 0.07, "critical_bypasses": True}},
        "avatar_bridge": {"input_mode": "direct", "presence_parameters": [], "hit_parameters": {}, "status_parameters": {}},
        "parameters": {
            "combat_enabled": "SoY_CombatEnabled", "osc_probe": "SoY_OSCProbe",
            "hit_weak": "SoY_HitWeak", "hit_average": "SoY_HitAverage", "hit_strong": "SoY_HitStrong", "hit_critical": "SoY_HitCritical", "hit_blocked": "SoY_HitBlocked",
            "debuff_burn": "SoY_DebuffBurn", "debuff_silence": "SoY_DebuffSilence", "debuff_freeze": "SoY_DebuffFreeze", "debuff_bind": "SoY_DebuffBind", "debuff_bleed": "SoY_DebuffBleed",
            "enemy_mode": "SoY_IsEnemy", "spell_type": "SoY_SpellType", "technick_type": "SoY_TechnickType", "item_type": "SoY_ItemType",
            "spell_active": "SoY_SpellActive", "technick_active": "SoY_TechnickActive", "item_active": "SoY_ItemActive",
            **{f"spell_bit_{i}": f"SoY_SpellBit{i}" for i in range(8)},
            **{f"technick_bit_{i}": f"SoY_TechnickBit{i}" for i in range(8)},
            **{f"item_bit_{i}": f"SoY_ItemBit{i}" for i in range(8)},
            "healing_source_enemy": "SoY_HealingSourceEnemy", "damage_source_enemy": "SoY_DamageSourceEnemy",
            "mist_charge": "SoY_MistCharge", "mist_max": "SoY_MistMax", "diablos_applicable": "SoY_DiablosApplicable", "diablos_percent": "SoY_DiablosPercent",
            "hp_percent": "SoY_HPPercent", "hp_stage": "SoY_HPStage", "critical_hp": "SoY_CriticalHP", "ko": "SoY_KO", "invulnerable": "SoY_Invulnerable",
            "burn_active": "SoY_BurnActive", "silenced": "SoY_Silenced", "frozen": "SoY_Frozen", "bound": "SoY_Bound", "bleeding": "SoY_Bleeding",
            "magic_locked": "SoY_MagicLocked", "movement_locked": "SoY_MovementLocked", "damage_reaction": "SoY_DamageReaction", "damaged": "SoY_Damaged", "healing": "SoY_Healing", "blocked": "SoY_Blocked",
        },
    }
    return BridgeController(config=config, state=state, send_parameter=lambda n, v: sent.append((n, v)), pulse_parameter=lambda n, v: None, event_sink=events.append)


def test_authoritative_remote_status_replaces_local_timer():
    state = make_state()
    state.apply_status("bleed", now=10.0)
    assert "bleed" in state.statuses
    assert state.replace_authoritative_statuses({"bleed"})
    assert "bleed" not in state.statuses
    assert "bleed" in state.external_statuses


def test_remote_clear_removes_stale_local_and_external_status():
    state = make_state()
    state.apply_status("bleed", now=10.0)
    state.external_statuses.add("bleed")
    state.set_external_status("bleed", False)
    assert "bleed" not in state.statuses
    assert "bleed" not in state.external_statuses


def test_authoritative_controller_does_not_tick_local_dot():
    state = make_state()
    state.apply_status("bleed", now=10.0)
    events, sent = [], []
    controller = make_controller(state, events, sent)
    before = state.current_hp
    controller.tick(now=20.0)
    assert state.current_hp == before
    assert not any(event.event == "dot_damage" for event in events)


def test_ko_rejects_direct_spell_selector_and_resets_avatar_parameter():
    state = make_state(hp=0)
    events, sent = [], []
    controller = make_controller(state, events, sent)
    controller._set_telemetry("spell_cast_type", 2, now=10.0, source="direct")
    assert controller.telemetry["spell_cast_type"] == 0
    assert ("SoY_SpellType", 0) in sent
    assert any(event.event == "action_ignored_ko" for event in events)


def test_critical_is_strictly_below_15_percent():
    state = make_state(hp=150)
    assert state.is_critical_hp is False
    state.set_hp(149)
    assert state.is_critical_hp is True
