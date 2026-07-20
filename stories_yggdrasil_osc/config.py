from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_DIR_NAME = "StoriesOfYggdrasil"
APP_SUBDIR_NAME = "OSCContactSystem"
CONFIG_FILENAME = "settings.json"
STATE_FILENAME = "runtime_state.json"
LOG_FILENAME = "events.log"

EXTERNAL_HIT_PARAMETERS = {
    "weak": [f"Hit By Weak Attack T{i}" for i in range(4)],
    "average": [f"Hit By Average Attack T{i}" for i in range(4)],
    "strong": [f"Hit By Strong Attack T{i}" for i in range(4)],
    "critical": [f"Hit By Critical Attack T{i}" for i in range(4)],
}

EXTERNAL_STATUS_PARAMETERS = {
    "burn": "DoT Burn",
    "bleed": "DoT Bleed",
    "silence": "Suppress Silence",
    "freeze": "Slow Freeze",
    "bind": "Slow Bind",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 13,
    "osc": {
        "listen_ip": "127.0.0.1",
        "listen_port": 9001,
        "vrchat_ip": "127.0.0.1",
        "vrchat_port": 9000,
        "auto_start_listener": True,
        "activity_timeout_seconds": 5.0,
    },
    "profile": {
        "name": "Local RP Character",
        "maximum_hp": 1000,
        "starting_hp": 1000,
        "critical_hp_percent": 0.25,
    },
    "combat": {
        "global_invulnerability_seconds": 1.0,
        "clear_statuses_when_disabled": True,
        "damage": {"weak": 40, "average": 100, "strong": 200, "critical": 400},
        "block": {
            "enabled": True,
            "window_seconds": 0.18,
            "hit_settle_seconds": 0.07,
            "critical_bypasses": True,
        },
    },
    "statuses": {
        "burn": {"duration_seconds": 12.0, "tick_seconds": 2.0, "damage": 20},
        "bleed": {"duration_seconds": 12.0, "tick_seconds": 2.0, "damage": 15},
        "silence": {"duration_seconds": 10.0},
        "freeze": {"duration_seconds": 4.0},
        "bind": {"duration_seconds": 6.0},
    },
    "avatar_bridge": {
        "input_mode": "auto",
        "health_parameter": "Health",
        "presence_parameters": ["Healthbar"],
        "block_parameter": "Hit Blocked",
        "hit_parameters": deepcopy(EXTERNAL_HIT_PARAMETERS),
        "status_parameters": deepcopy(EXTERNAL_STATUS_PARAMETERS),
        "family_dedupe_seconds": 0.10,
        "observe_health": True,
        "health_invert": True,
        "suppress_direct_damage": True,
    },
    "sam": {
        "enabled": False,
        "base_url": "https://admin.storiesofyggdrasil.com/api/osc",
        "token": "",
        "device_name": "Stories OSC Desktop",
        "auto_poll": True,
        "poll_seconds": 2.0,
        "push_debounce_seconds": 0.30,
        "sync_hp": True,
        "sync_statuses": True,
        "sync_combat_toggle": True,
        "pull_remote_changes": True,
        "drive_avatar_health_from_sam": False,
        "drive_avatar_statuses_from_sam": False,
    },
    "npc_mode": {
        "enabled": False,
        "enemy_key": "",
        "enemy_name": "",
    },
    "updates": {
        "github_repo": "",
        "check_on_start": True,
        "channel": "stable",
        "asset_pattern": "Stories_Of_Yggdrasil_OSC_Windows",
    },
    "parameters": {
        "combat_enabled": "SoY_CombatEnabled",
        "osc_probe": "SoY_OSCProbe",
        "hit_weak": "SoY_HitWeak",
        "hit_average": "SoY_HitAverage",
        "hit_strong": "SoY_HitStrong",
        "hit_critical": "SoY_HitCritical",
        "hit_blocked": "SoY_HitBlocked",
        "debuff_burn": "SoY_DebuffBurn",
        "debuff_silence": "SoY_DebuffSilence",
        "debuff_freeze": "SoY_DebuffFreeze",
        "debuff_bind": "SoY_DebuffBind",
        "debuff_bleed": "SoY_DebuffBleed",
        "hp_percent": "SoY_HPPercent",
        "hp_stage": "SoY_HPStage",
        "damage_reaction": "SoY_DamageReaction",
        "damaged": "SoY_Damaged",
        "healing": "SoY_Healing",
        "critical_hp": "SoY_CriticalHP",
        "ko": "SoY_KO",
        "invulnerable": "SoY_Invulnerable",
        "blocked": "SoY_Blocked",
        "burn_active": "SoY_BurnActive",
        "silenced": "SoY_Silenced",
        "frozen": "SoY_Frozen",
        "bound": "SoY_Bound",
        "bleeding": "SoY_Bleeding",
        "magic_locked": "SoY_MagicLocked",
        "movement_locked": "SoY_MovementLocked",
        "enemy_mode": "SoY_IsEnemy",
        "spell_type": "SoY_SpellType",
        "spell_active": "SoY_SpellActive",
        "spell_bit_0": "SoY_SpellBit0",
        "spell_bit_1": "SoY_SpellBit1",
        "spell_bit_2": "SoY_SpellBit2",
        "spell_bit_3": "SoY_SpellBit3",
        "spell_bit_4": "SoY_SpellBit4",
        "spell_bit_5": "SoY_SpellBit5",
        "spell_bit_6": "SoY_SpellBit6",
        "spell_bit_7": "SoY_SpellBit7",
        "technick_type": "SoY_TechnickType",
        "technick_active": "SoY_TechnickActive",
        "technick_bit_0": "SoY_TechnickBit0",
        "technick_bit_1": "SoY_TechnickBit1",
        "technick_bit_2": "SoY_TechnickBit2",
        "technick_bit_3": "SoY_TechnickBit3",
        "technick_bit_4": "SoY_TechnickBit4",
        "technick_bit_5": "SoY_TechnickBit5",
        "technick_bit_6": "SoY_TechnickBit6",
        "technick_bit_7": "SoY_TechnickBit7",
        "item_type": "SoY_ItemType",
        "item_active": "SoY_ItemActive",
        "item_bit_0": "SoY_ItemBit0",
        "item_bit_1": "SoY_ItemBit1",
        "item_bit_2": "SoY_ItemBit2",
        "item_bit_3": "SoY_ItemBit3",
        "item_bit_4": "SoY_ItemBit4",
        "item_bit_5": "SoY_ItemBit5",
        "item_bit_6": "SoY_ItemBit6",
        "item_bit_7": "SoY_ItemBit7",
        "healing_source_enemy": "SoY_HealingSourceEnemy",
        "healing_rejected": "SoY_HealingRejected",
        "mist_charge": "SoY_MistCharge",
        "mist_max": "SoY_MistMax",
        "mist_percent": "SoY_MistPercent",
        "diablos_applicable": "SoY_DiablosApplicable",
        "diablos_percent": "SoY_DiablosPercent",
    },
}


def get_app_data_dir() -> Path:
    if os.name == "nt":
        root = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = root / APP_DIR_NAME / APP_SUBDIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    return get_app_data_dir() / CONFIG_FILENAME


def get_state_path() -> Path:
    return get_app_data_dir() / STATE_FILENAME


def get_log_path() -> Path:
    return get_app_data_dir() / LOG_FILENAME


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _migrate_avatar_bridge(raw: dict[str, Any], config: dict[str, Any]) -> None:
    """Move settings from pre-0.7 compatibility keys without exposing old branding."""
    old_section = raw.get("compatibility")
    if not isinstance(old_section, dict):
        return
    old_prefix = "sh" + "room"
    bridge = config.setdefault("avatar_bridge", {})
    mapping = {
        "input_mode": "input_mode",
        f"{old_prefix}_health_parameter": "health_parameter",
        f"{old_prefix}_presence_parameters": "presence_parameters",
        f"{old_prefix}_block_parameter": "block_parameter",
        f"{old_prefix}_hit_parameters": "hit_parameters",
        f"{old_prefix}_status_parameters": "status_parameters",
        "family_dedupe_seconds": "family_dedupe_seconds",
        f"auto_observe_{old_prefix}_health": "observe_health",
        f"{old_prefix}_health_invert": "health_invert",
        f"suppress_bridge_damage_for_{old_prefix}": "suppress_direct_damage",
    }
    for old_key, new_key in mapping.items():
        if old_key in old_section:
            bridge[new_key] = deepcopy(old_section[old_key])
    old_mode = str(bridge.get("input_mode", "auto")).lower()
    bridge["input_mode"] = {old_prefix: "external", "soy": "direct"}.get(old_mode, old_mode)

    sam_cfg = config.setdefault("sam", {})
    for old_key, new_key in (
        (f"drive_{old_prefix}_health_from_sam", "drive_avatar_health_from_sam"),
        (f"drive_{old_prefix}_statuses_from_sam", "drive_avatar_statuses_from_sam"),
    ):
        if old_key in sam_cfg:
            sam_cfg[new_key] = bool(sam_cfg.get(old_key))


def load_config() -> dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        config = deepcopy(DEFAULT_CONFIG)
        save_config(config)
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Settings root must be an object.")
        config = _deep_merge(DEFAULT_CONFIG, raw)
        _migrate_avatar_bridge(raw, config)
        config["version"] = 13
        sam_cfg = config.setdefault("sam", {})
        if str(sam_cfg.get("base_url") or "").strip().rstrip("/") in {
            "http://127.0.0.1:8766",
            "http://localhost:8766",
            "https://storiesofyggdrasil.com/api/osc",
        }:
            sam_cfg["base_url"] = "https://admin.storiesofyggdrasil.com/api/osc"
        return config
    except Exception:
        backup = path.with_name(path.stem + ".invalid.json")
        try:
            path.replace(backup)
        except Exception:
            pass
        config = deepcopy(DEFAULT_CONFIG)
        save_config(config)
        return config


def save_config(config: dict[str, Any]) -> None:
    path = get_config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_runtime_state(default_hp: int) -> dict[str, Any]:
    path = get_state_path()
    if not path.exists():
        return {"current_hp": int(default_hp), "combat_enabled": False}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"current_hp": int(default_hp), "combat_enabled": False}
    except Exception:
        return {"current_hp": int(default_hp), "combat_enabled": False}


def save_runtime_state(state: dict[str, Any]) -> None:
    path = get_state_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
