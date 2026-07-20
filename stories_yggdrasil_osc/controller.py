from __future__ import annotations

import heapq
import math
import time
from collections.abc import Callable
from typing import Any

from .combat import CombatState
from .models import EventResult, PendingHit


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class BridgeController:
    """Translate VRChat OSC parameters into local combat/status events.

    Two input contracts are supported:
      * SoY direct parameters, used by the lightweight receiver installer.
      * Existing avatar health/contact parameters, used by avatars that already
        own a compatible health controller.

    SoY_CombatEnabled is always authoritative for RP-combat opt-in, even when
    strict external input mode is selected. Healthbar is
    treated as presence/UI state only and never as combat opt-in.
    """

    REACTION_CODES = {
        "weak": 1,
        "average": 2,
        "strong": 3,
        "critical": 4,
        "blocked": 5,
        "burn": 6,
        "bleed": 7,
        "healing": 8,
    }

    def __init__(
        self,
        *,
        config: dict[str, Any],
        state: CombatState,
        send_parameter: Callable[[str, Any], None],
        pulse_parameter: Callable[[str, float], None],
        event_sink: Callable[[EventResult], None],
    ) -> None:
        self.config = config
        self.state = state
        self.send_parameter = send_parameter
        self.pulse_parameter = pulse_parameter
        self.event_sink = event_sink
        self.parameters: dict[str, str] = {}
        self._direct_input_by_name: dict[str, tuple[str, str | None]] = {}
        self._external_input_by_name: dict[str, tuple[str, str | None]] = {}
        self._last_bool_values: dict[str, bool] = {}
        self._last_family_event_at: dict[str, float] = {}
        self._last_direct_action_value: dict[str, int] = {}
        self._pending_hits: list[tuple[float, int, PendingHit]] = []
        self._pending_counter = 0
        self._spell_bus_active = False
        self._spell_bus_bits = [False] * 8
        self._spell_bus_pending_until = 0.0
        self._technick_bus_active = False
        self._technick_bus_bits = [False] * 8
        self._technick_bus_pending_until = 0.0
        self._item_bus_active = False
        self._item_bus_bits = [False] * 8
        self._item_bus_pending_until = 0.0
        self._action_bus_settle_seconds = 0.03
        self.current_avatar_id = ""
        self.last_input_at = 0.0
        self.external_detected = False
        self.last_external_parameter = ""
        self.telemetry: dict[str, Any] = {
            "enemy_mode": False,
            # Direct Int parameters are local menu actions from this avatar.
            # Binary Contact buses are incoming effects received by this avatar.
            "spell_cast_type": 0,
            "technick_use_type": 0,
            "item_use_type": 0,
            "spell_type": 0,
            "technick_type": 0,
            "item_type": 0,
            "healing_source_enemy": False,
            "mist_charge": 0,
            "mist_max": 0,
            "diablos_applicable": False,
            "diablos_percent": 0,
            "hit_event": "",
        }
        self.reconfigure(config)

    def reconfigure(self, config: dict[str, Any]) -> None:
        self.config = config
        self.parameters = config["parameters"]
        self._direct_input_by_name = {
            self.parameters["combat_enabled"]: ("combat_enabled", None),
            self.parameters.get("osc_probe", "SoY_OSCProbe"): ("osc_probe", None),
            self.parameters["hit_weak"]: ("hit", "weak"),
            self.parameters["hit_average"]: ("hit", "average"),
            self.parameters["hit_strong"]: ("hit", "strong"),
            self.parameters["hit_critical"]: ("hit", "critical"),
            self.parameters["hit_blocked"]: ("block", None),
            self.parameters["debuff_burn"]: ("status", "burn"),
            self.parameters["debuff_silence"]: ("status", "silence"),
            self.parameters["debuff_freeze"]: ("status", "freeze"),
            self.parameters["debuff_bind"]: ("status", "bind"),
            self.parameters["debuff_bleed"]: ("status", "bleed"),
            self.parameters.get("enemy_mode", "SoY_IsEnemy"): ("telemetry_bool", "enemy_mode"),
            self.parameters.get("spell_type", "SoY_SpellType"): ("telemetry_int", "spell_cast_type"),
            self.parameters.get("spell_active", "SoY_SpellActive"): ("spell_bus_active", None),
            self.parameters.get("spell_bit_0", "SoY_SpellBit0"): ("spell_bus_bit", "0"),
            self.parameters.get("spell_bit_1", "SoY_SpellBit1"): ("spell_bus_bit", "1"),
            self.parameters.get("spell_bit_2", "SoY_SpellBit2"): ("spell_bus_bit", "2"),
            self.parameters.get("spell_bit_3", "SoY_SpellBit3"): ("spell_bus_bit", "3"),
            self.parameters.get("spell_bit_4", "SoY_SpellBit4"): ("spell_bus_bit", "4"),
            self.parameters.get("spell_bit_5", "SoY_SpellBit5"): ("spell_bus_bit", "5"),
            self.parameters.get("spell_bit_6", "SoY_SpellBit6"): ("spell_bus_bit", "6"),
            self.parameters.get("spell_bit_7", "SoY_SpellBit7"): ("spell_bus_bit", "7"),
            self.parameters.get("technick_type", "SoY_TechnickType"): ("telemetry_int", "technick_use_type"),
            self.parameters.get("technick_active", "SoY_TechnickActive"): ("technick_bus_active", None),
            self.parameters.get("technick_bit_0", "SoY_TechnickBit0"): ("technick_bus_bit", "0"),
            self.parameters.get("technick_bit_1", "SoY_TechnickBit1"): ("technick_bus_bit", "1"),
            self.parameters.get("technick_bit_2", "SoY_TechnickBit2"): ("technick_bus_bit", "2"),
            self.parameters.get("technick_bit_3", "SoY_TechnickBit3"): ("technick_bus_bit", "3"),
            self.parameters.get("technick_bit_4", "SoY_TechnickBit4"): ("technick_bus_bit", "4"),
            self.parameters.get("technick_bit_5", "SoY_TechnickBit5"): ("technick_bus_bit", "5"),
            self.parameters.get("technick_bit_6", "SoY_TechnickBit6"): ("technick_bus_bit", "6"),
            self.parameters.get("technick_bit_7", "SoY_TechnickBit7"): ("technick_bus_bit", "7"),
            self.parameters.get("item_type", "SoY_ItemType"): ("telemetry_int", "item_use_type"),
            self.parameters.get("item_active", "SoY_ItemActive"): ("item_bus_active", None),
            self.parameters.get("item_bit_0", "SoY_ItemBit0"): ("item_bus_bit", "0"),
            self.parameters.get("item_bit_1", "SoY_ItemBit1"): ("item_bus_bit", "1"),
            self.parameters.get("item_bit_2", "SoY_ItemBit2"): ("item_bus_bit", "2"),
            self.parameters.get("item_bit_3", "SoY_ItemBit3"): ("item_bus_bit", "3"),
            self.parameters.get("item_bit_4", "SoY_ItemBit4"): ("item_bus_bit", "4"),
            self.parameters.get("item_bit_5", "SoY_ItemBit5"): ("item_bus_bit", "5"),
            self.parameters.get("item_bit_6", "SoY_ItemBit6"): ("item_bus_bit", "6"),
            self.parameters.get("item_bit_7", "SoY_ItemBit7"): ("item_bus_bit", "7"),
            self.parameters.get("healing_source_enemy", "SoY_HealingSourceEnemy"): ("telemetry_bool", "healing_source_enemy"),
            self.parameters.get("mist_charge", "SoY_MistCharge"): ("telemetry_int", "mist_charge"),
            self.parameters.get("mist_max", "SoY_MistMax"): ("telemetry_int", "mist_max"),
            self.parameters.get("diablos_applicable", "SoY_DiablosApplicable"): ("telemetry_bool", "diablos_applicable"),
            self.parameters.get("diablos_percent", "SoY_DiablosPercent"): ("telemetry_percent", "diablos_percent"),
        }

        compat = config.get("avatar_bridge", {})
        external: dict[str, tuple[str, str | None]] = {
            str(compat.get("health_parameter", "Health")): ("health", None),
            str(compat.get("block_parameter", "Hit Blocked")): ("block", None),
        }
        # Healthbar is display state only. It may identify a compatible controller,
        # but it must not enable or disable RP
        # combat in the desktop bridge.
        for presence_name in compat.get("presence_parameters", ["Healthbar"]) or []:
            if str(presence_name).strip():
                external[str(presence_name).strip()] = ("presence", None)
        for hit_type, names in (compat.get("hit_parameters", {}) or {}).items():
            for name in names or []:
                external[str(name)] = ("hit", str(hit_type).lower())
        for status, name in (compat.get("status_parameters", {}) or {}).items():
            external[str(name)] = ("external_status", str(status).lower())
        self._external_input_by_name = external

    @property
    def configured_input_mode(self) -> str:
        mode = str(self.config.get("avatar_bridge", {}).get("input_mode", "auto")).strip().lower()
        return mode if mode in {"auto", "external", "direct"} else "auto"

    @property
    def active_input_mode(self) -> str:
        mode = self.configured_input_mode
        if mode == "external" or (mode == "auto" and self.external_detected):
            return "external"
        return "direct"

    def reset_edges(self) -> None:
        self._last_bool_values.clear()
        self._last_family_event_at.clear()
        self._pending_hits.clear()
        self._spell_bus_active = False
        self._spell_bus_bits = [False] * 8
        self._spell_bus_pending_until = 0.0

    def handle_osc(self, address: str, values: tuple[Any, ...], now: float | None = None) -> None:
        t = time.monotonic() if now is None else float(now)
        self.last_input_at = t
        if address == "/avatar/change":
            self.current_avatar_id = str(values[0]) if values else ""
            self.external_detected = False
            self.last_external_parameter = ""
            self.reset_edges()
            self.sync_outputs()
            return

        prefix = "/avatar/parameters/"
        if not address.startswith(prefix) or not values:
            return
        name = address[len(prefix):]

        mode = self.configured_input_mode

        # Stories control parameters must work avatar -> desktop in every input
        # mode. External mode applies only to legacy health/hit/status inputs;
        # it must never suppress RP Combat, Enemy Mode, action Ints, or the
        # incoming Spell/Technick/Item binary buses.
        direct_entry = self._direct_input_by_name.get(name)
        always_direct_kinds = {
            "combat_enabled", "osc_probe",
            "telemetry_bool", "telemetry_int", "telemetry_percent",
            "spell_bus_active", "spell_bus_bit",
            "technick_bus_active", "technick_bus_bit",
            "item_bus_active", "item_bus_bit",
        }
        if direct_entry is not None and direct_entry[0] in always_direct_kinds:
            self._handle_input(name, direct_entry, values[0], t, source="direct")
            return

        external_entry = self._external_input_by_name.get(name)
        if external_entry is not None and mode in {"auto", "external"}:
            self._mark_external_detected(name)
            self._handle_input(name, external_entry, values[0], t, source="external")
            return

        if direct_entry is None or mode == "external":
            return
        # In auto mode, prefer existing avatar hit/status signals once detected.
        # SoY_CombatEnabled was handled above and is never filtered.
        if mode == "auto" and self.external_detected:
            return
        self._handle_input(name, direct_entry, values[0], t, source="direct")

    def _handle_input(
        self,
        name: str,
        entry: tuple[str, str | None],
        raw_value: Any,
        now: float,
        *,
        source: str,
    ) -> None:
        kind, detail = entry
        if kind == "health":
            if bool(self.config.get("avatar_bridge", {}).get("observe_health", True)):
                self._handle_observed_health(raw_value, source="external")
            return
        if kind == "presence":
            return

        if kind in {"spell_bus_bit", "technick_bus_bit", "item_bus_bit"} and detail is not None:
            try:
                bit = int(detail)
            except (TypeError, ValueError):
                return
            bus_name = kind.replace("_bus_bit", "")
            bits = getattr(self, f"_{bus_name}_bus_bits")
            if 0 <= bit < len(bits):
                bits[bit] = _as_bool(raw_value)
                if bool(getattr(self, f"_{bus_name}_bus_active")):
                    setattr(self, f"_{bus_name}_bus_pending_until", now + self._action_bus_settle_seconds)
            return

        if kind in {"spell_bus_active", "technick_bus_active", "item_bus_active"}:
            bus_name = kind.replace("_bus_active", "")
            active = _as_bool(raw_value)
            setattr(self, f"_{bus_name}_bus_active", active)
            if active:
                # Contact parameters arrive as separate OSC packets. Give the bit
                # values a few milliseconds to settle before resolving the ID.
                setattr(self, f"_{bus_name}_bus_pending_until", now + self._action_bus_settle_seconds)
            else:
                setattr(self, f"_{bus_name}_bus_pending_until", 0.0)
                self.telemetry[f"{bus_name}_type"] = 0
            return

        if kind in {"telemetry_bool", "telemetry_int", "telemetry_percent"} and detail:
            if kind == "telemetry_bool":
                value = _as_bool(raw_value)
            elif kind == "telemetry_percent":
                try:
                    raw = float(raw_value or 0.0)
                    if not math.isfinite(raw):
                        raw = 0.0
                except (TypeError, ValueError):
                    raw = 0.0
                # Avatar radial Floats are normalized. Accept old 0..100 senders too.
                value = int(round(max(0.0, min(100.0, raw if raw > 1.0 else raw * 100.0))))
            else:
                value = int(float(raw_value or 0))
            self._set_telemetry(detail, value, now=now, source="direct_parameter")
            return

        value = _as_bool(raw_value)
        edge_key = f"{source}:{name}"
        previous = self._last_bool_values.get(edge_key, False)
        self._last_bool_values[edge_key] = value

        if kind == "osc_probe":
            if previous != value:
                snap = self.state.snapshot(now)
                self._emit(EventResult(
                    True,
                    "osc_probe",
                    f"OSC probe parameter observed from VRChat: {value}.",
                    hp_before=snap["current_hp"],
                    hp_after=snap["current_hp"],
                    maximum_hp=snap["maximum_hp"],
                    metadata={"value": value, "source": source, "parameter": name},
                ))
            return

        if kind == "combat_enabled":
            if self.state.combat_enabled != value:
                self._emit(self.state.set_combat_enabled(value))
            # Echo an acknowledgement so the avatar and desktop converge even
            # after avatar changes or a dropped outbound packet.
            self.send_parameter(self.parameters["combat_enabled"], value)
            self.sync_outputs()
            return

        if kind == "external_status" and detail:
            # Existing status outputs are persistent state parameters, not OnEnter
            # pulses. Mirror both edges without applying a second DOT copy.
            if previous != value:
                result = self.state.set_external_status(detail, value, now=now)
                self._emit(result)
                self.sync_outputs()
            return

        if not value or previous:
            return

        if kind == "block":
            rule = self.config["combat"]["block"]
            if rule.get("enabled", True):
                result = self.state.record_block(float(rule.get("window_seconds", 0.18)), now=now)
                self._emit(result)
                if result.accepted:
                    self._send_reaction(self.REACTION_CODES["blocked"], blocked=True)
            return

        if kind == "hit" and detail:
            self.telemetry["hit_event"] = detail
            if source == "external" and self._family_duplicate(detail, now):
                snap = self.state.snapshot(now)
                self._emit(EventResult(
                    False,
                    "duplicate_hit_ignored",
                    f"Duplicate {detail.title()} contact pulse ignored.",
                    hp_before=snap["current_hp"],
                    hp_after=snap["current_hp"],
                    maximum_hp=snap["maximum_hp"],
                    metadata={"hit_type": detail, "source": source},
                ))
                return
            self.queue_hit(detail, now=now, source=source)
            return

        if kind == "status" and detail:
            result = self.state.apply_status(detail, now=now)
            self._emit(result)
            self.sync_outputs()

    def _set_telemetry(self, detail: str, value: Any, *, now: float, source: str) -> None:
        previous = self.telemetry.get(detail)
        action_fields = {
            "spell_cast_type", "technick_use_type", "item_use_type",
            "spell_type", "technick_type", "item_type",
        }
        direct_fields = {"spell_cast_type", "technick_use_type", "item_use_type"}
        numeric_value = int(value or 0) if detail in action_fields else 0

        # The payload builder clears one-shot telemetry after submission. Keep a
        # separate raw-parameter latch so a repeated OSC packet while a VRChat
        # Button is still held cannot charge MP or consume an item twice.
        if detail in direct_fields:
            if numeric_value == 0:
                self._last_direct_action_value.pop(detail, None)
            elif self._last_direct_action_value.get(detail) == numeric_value:
                self.telemetry[detail] = numeric_value
                return
            else:
                self._last_direct_action_value[detail] = numeric_value

        self.telemetry[detail] = value
        if detail in action_fields and numeric_value == 0:
            return
        if previous != value:
            snap = self.state.snapshot(now)
            self._emit(EventResult(
                True,
                "telemetry",
                f"{detail.replace('_', ' ').title()}: {value}",
                hp_before=snap["current_hp"],
                hp_after=snap["current_hp"],
                maximum_hp=snap["maximum_hp"],
                metadata={detail: value, "source": source},
            ))

    def _resolve_action_bus(self, bus_name: str, now: float) -> None:
        if not bool(getattr(self, f"_{bus_name}_bus_active")):
            return
        bits = getattr(self, f"_{bus_name}_bus_bits")
        action_id = sum((1 << bit) for bit, enabled in enumerate(bits) if enabled)
        if action_id <= 0:
            return
        self._set_telemetry(f"{bus_name}_type", action_id, now=now, source=f"{bus_name}_binary_contact_bus")

    def _mark_external_detected(self, parameter: str) -> None:
        first = not self.external_detected
        self.external_detected = True
        self.last_external_parameter = parameter
        if first:
            snap = self.state.snapshot()
            self._emit(EventResult(
                True,
                "external_detected",
                f"Compatible avatar health input detected from '{parameter}'.",
                hp_before=snap["current_hp"],
                hp_after=snap["current_hp"],
                maximum_hp=snap["maximum_hp"],
                metadata={"parameter": parameter},
            ))

    def _family_duplicate(self, hit_type: str, now: float) -> bool:
        dedupe = max(0.0, float(self.config.get("avatar_bridge", {}).get("family_dedupe_seconds", 0.10)))
        previous = self._last_family_event_at.get(hit_type, -10_000.0)
        self._last_family_event_at[hit_type] = now
        return now - previous < dedupe

    def _external_health_owns_damage(self, source: str) -> bool:
        if source == "external" and bool(self.config.get("avatar_bridge", {}).get("suppress_direct_damage", True)):
            return True
        return False

    def queue_hit(self, hit_type: str, now: float | None = None, *, source: str = "direct") -> None:
        t = time.monotonic() if now is None else float(now)
        block = self.config["combat"]["block"]
        settle = 0.0 if hit_type == "critical" else max(0.0, float(block.get("hit_settle_seconds", 0.07)))
        pending = PendingHit(
            hit_type=hit_type,
            due_at=t + settle,
            received_at=t,
            source=source,
            external_health_owns_damage=self._external_health_owns_damage(source),
        )
        self._pending_counter += 1
        heapq.heappush(self._pending_hits, (pending.due_at, self._pending_counter, pending))

    def manual_hit(self, hit_type: str, now: float | None = None) -> EventResult:
        t = time.monotonic() if now is None else float(now)
        block_cfg = self.config["combat"]["block"]
        critical_bypass = bool(block_cfg.get("critical_bypasses", True))
        blocked = bool(block_cfg.get("enabled", True)) and self.state.is_blocking(t) and not (hit_type == "critical" and critical_bypass)
        result = self.state.apply_hit(hit_type, now=t, blocked=blocked)
        self._emit(result)
        self._after_result(result)
        return result

    def manual_status(self, name: str, now: float | None = None) -> EventResult:
        result = self.state.apply_status(name, now=now)
        self._emit(result)
        self.sync_outputs()
        return result

    def commit_result(self, result: EventResult) -> EventResult:
        self._emit(result)
        self._after_result(result)
        return result

    def tick(self, now: float | None = None) -> None:
        t = time.monotonic() if now is None else float(now)
        for bus_name in ("spell", "technick", "item"):
            pending_attr = f"_{bus_name}_bus_pending_until"
            pending_until = float(getattr(self, pending_attr))
            if pending_until and pending_until <= t:
                setattr(self, pending_attr, 0.0)
                self._resolve_action_bus(bus_name, t)
        while self._pending_hits and self._pending_hits[0][0] <= t:
            _, _, pending = heapq.heappop(self._pending_hits)
            block_cfg = self.config["combat"]["block"]
            critical_bypass = bool(block_cfg.get("critical_bypasses", True))
            blocked = bool(block_cfg.get("enabled", True)) and self.state.is_blocking(t) and not (
                pending.hit_type == "critical" and critical_bypass
            )
            snap = self.state.snapshot(t)
            if not snap["combat_enabled"]:
                result = EventResult(
                    False,
                    "hit_ignored",
                    f"{pending.hit_type.title()} hit ignored: RP combat is disabled.",
                    hp_before=snap["current_hp"],
                    hp_after=snap["current_hp"],
                    maximum_hp=snap["maximum_hp"],
                    metadata={"hit_type": pending.hit_type, "source": pending.source},
                )
            elif blocked:
                result = EventResult(
                    True,
                    "blocked",
                    f"{pending.hit_type.title()} attack blocked.",
                    hp_before=snap["current_hp"],
                    hp_after=snap["current_hp"],
                    maximum_hp=snap["maximum_hp"],
                    reaction_code=self.REACTION_CODES["blocked"],
                    metadata={"hit_type": pending.hit_type, "source": pending.source},
                )
            elif pending.external_health_owns_damage:
                result = EventResult(
                    True,
                    "external_hit_observed",
                    f"Observed {pending.hit_type.title()} hit; the avatar health controller owns damage.",
                    hp_before=snap["current_hp"],
                    hp_after=snap["current_hp"],
                    maximum_hp=snap["maximum_hp"],
                    reaction_code=self.REACTION_CODES.get(pending.hit_type, 0),
                    metadata={"hit_type": pending.hit_type, "source": pending.source},
                )
            else:
                result = self.state.apply_hit(pending.hit_type, now=t, blocked=False)
            self._emit(result)
            self._after_result(result)

        for result in self.state.tick(t):
            self._emit(result)
            self._after_result(result)
        self.sync_timed_outputs(t)

    def _after_result(self, result: EventResult) -> None:
        if result.event in {"damage", "dot_damage", "external_hit_observed"}:
            self._send_reaction(result.reaction_code, damaged=True)
        elif result.event == "blocked":
            self._send_reaction(self.REACTION_CODES["blocked"], blocked=True)
        elif result.event in {"healing", "revive"}:
            self._send_reaction(self.REACTION_CODES["healing"], healing=True)
        self.sync_outputs()

    def _send_reaction(self, code: int, *, damaged: bool = False, healing: bool = False, blocked: bool = False) -> None:
        self.send_parameter(self.parameters["damage_reaction"], int(code))
        if damaged:
            self.pulse_parameter(self.parameters["damaged"], 0.15)
        if healing:
            self.pulse_parameter(self.parameters["healing"], 0.18)
        if blocked:
            self.pulse_parameter(self.parameters.get("blocked", "SoY_Blocked"), 0.15)

    def sync_timed_outputs(self, now: float | None = None) -> None:
        snap = self.state.snapshot(now)
        self.send_parameter(self.parameters["invulnerable"], bool(snap["invulnerable"]))

    def sync_outputs(self) -> None:
        snap = self.state.snapshot()
        self.send_parameter(self.parameters["hp_percent"], float(snap["hp_ratio"]))
        self.send_parameter(self.parameters["hp_stage"], int(snap["hp_stage"]))
        self.send_parameter(self.parameters["critical_hp"], bool(snap["critical_hp"]))
        self.send_parameter(self.parameters["ko"], bool(snap["is_ko"]))
        self.send_parameter(self.parameters["invulnerable"], bool(snap["invulnerable"]))
        active = snap["statuses"]
        self.send_parameter(self.parameters.get("burn_active", "SoY_BurnActive"), "burn" in active)
        self.send_parameter(self.parameters.get("silenced", "SoY_Silenced"), "silence" in active)
        self.send_parameter(self.parameters.get("frozen", "SoY_Frozen"), "freeze" in active)
        self.send_parameter(self.parameters.get("bound", "SoY_Bound"), "bind" in active)
        self.send_parameter(self.parameters.get("bleeding", "SoY_Bleeding"), "bleed" in active)
        self.send_parameter(self.parameters.get("magic_locked", "SoY_MagicLocked"), bool(snap["magic_locked"]))
        self.send_parameter(self.parameters.get("movement_locked", "SoY_MovementLocked"), bool(snap["movement_locked"]))

    def _handle_observed_health(self, raw_value: Any, *, source: str) -> None:
        try:
            ratio = float(raw_value)
        except Exception:
            return
        ratio = max(0.0, min(1.0, ratio))
        # Existing avatar controllers commonly expose accumulated damage:
        # 0.0 = full health, 1.0 = KO.
        if bool(self.config.get("avatar_bridge", {}).get("health_invert", True)):
            ratio = 1.0 - ratio
        result = self.state.set_hp(round(self.state.maximum_hp * ratio))
        observed = EventResult(
            True,
            "external_health_update",
            f"Observed {source.upper()} health: {result.hp_after}/{result.maximum_hp}.",
            amount=result.amount,
            hp_before=result.hp_before,
            hp_after=result.hp_after,
            maximum_hp=result.maximum_hp,
            metadata={"source": source, "raw_value": raw_value},
        )
        self._emit(observed)
        self.sync_outputs()

    def _emit(self, result: EventResult) -> None:
        self.event_sink(result)
