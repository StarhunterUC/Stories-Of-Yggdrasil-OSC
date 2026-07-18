from __future__ import annotations

import heapq
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
        self._pending_hits: list[tuple[float, int, PendingHit]] = []
        self._pending_counter = 0
        self.current_avatar_id = ""
        self.last_input_at = 0.0
        self.external_detected = False
        self.last_external_parameter = ""
        self.telemetry: dict[str, Any] = {"enemy_mode": False, "spell_type": 0, "healing_source_enemy": False, "mist_charge": 0, "mist_max": 0, "diablos_applicable": False, "diablos_percent": 0, "hit_event": ""}
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
            self.parameters.get("spell_type", "SoY_SpellType"): ("telemetry_int", "spell_type"),
            self.parameters.get("healing_source_enemy", "SoY_HealingSourceEnemy"): ("telemetry_bool", "healing_source_enemy"),
            self.parameters.get("mist_charge", "SoY_MistCharge"): ("telemetry_int", "mist_charge"),
            self.parameters.get("mist_max", "SoY_MistMax"): ("telemetry_int", "mist_max"),
            self.parameters.get("diablos_applicable", "SoY_DiablosApplicable"): ("telemetry_bool", "diablos_applicable"),
            self.parameters.get("diablos_percent", "SoY_DiablosPercent"): ("telemetry_int", "diablos_percent"),
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

        # The Stories RP Combat menu toggle must work avatar -> desktop in every
        # input mode. Older builds accidentally ignored it in strict external
        # mode, while desktop -> avatar still worked.
        direct_entry = self._direct_input_by_name.get(name)
        if direct_entry is not None and direct_entry[0] in {"combat_enabled", "osc_probe"}:
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

        if kind in {"telemetry_bool", "telemetry_int"} and detail:
            value = _as_bool(raw_value) if kind == "telemetry_bool" else int(float(raw_value or 0))
            previous = self.telemetry.get(detail)
            self.telemetry[detail] = value
            if detail == "spell_type" and int(value or 0) == 0:
                return
            if previous != value:
                snap = self.state.snapshot(now)
                self._emit(EventResult(True, "telemetry", f"{detail.replace('_', ' ').title()}: {value}", hp_before=snap["current_hp"], hp_after=snap["current_hp"], maximum_hp=snap["maximum_hp"], metadata={detail: value}))
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
