from __future__ import annotations

import threading
import time
from typing import Any

from .models import ActiveStatus, EventResult


class CombatState:
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
        maximum_hp: int,
        current_hp: int,
        damage_values: dict[str, int],
        invulnerability_seconds: float,
        critical_hp_percent: float,
        status_rules: dict[str, dict[str, Any]],
        clear_statuses_when_disabled: bool = True,
        combat_enabled: bool = False,
    ) -> None:
        self._lock = threading.RLock()
        self.maximum_hp = max(1, int(maximum_hp))
        self.current_hp = max(0, min(self.maximum_hp, int(current_hp)))
        self.damage_values = {
            "weak": max(0, int(damage_values.get("weak", 40))),
            "average": max(0, int(damage_values.get("average", 100))),
            "strong": max(0, int(damage_values.get("strong", 200))),
            "critical": max(0, int(damage_values.get("critical", 400))),
        }
        self.invulnerability_seconds = max(0.0, float(invulnerability_seconds))
        self.critical_hp_percent = max(0.01, min(0.99, float(critical_hp_percent)))
        self.status_rules = status_rules
        self.clear_statuses_when_disabled = bool(clear_statuses_when_disabled)
        self.combat_enabled = bool(combat_enabled)
        self.invulnerable_until = 0.0
        self.blocked_until = 0.0
        self.statuses: dict[str, ActiveStatus] = {}
        # Persistent status values observed from an external SHR00M controller.
        # They are mirrors only and never apply a second copy of DOT damage.
        self.external_statuses: set[str] = set()

    @property
    def hp_ratio(self) -> float:
        with self._lock:
            return max(0.0, min(1.0, self.current_hp / self.maximum_hp))

    @property
    def hp_stage(self) -> int:
        return max(0, min(10, round(self.hp_ratio * 10)))

    @property
    def is_ko(self) -> bool:
        with self._lock:
            return self.current_hp <= 0

    @property
    def is_critical_hp(self) -> bool:
        with self._lock:
            return 0 < self.current_hp <= round(self.maximum_hp * self.critical_hp_percent)

    def is_invulnerable(self, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            return t < self.invulnerable_until

    def is_blocking(self, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            return t < self.blocked_until

    def status_active(self, name: str, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            key = str(name).lower()
            if key in self.external_statuses:
                return True
            status = self.statuses.get(key)
            return bool(status and status.expires_at > t)

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            active = {
                key: {
                    "remaining": status.remaining(t),
                    "expires_at": status.expires_at,
                    "next_tick_at": status.next_tick_at,
                    "external": False,
                }
                for key, status in self.statuses.items()
                if status.expires_at > t
            }
            for key in self.external_statuses:
                active[key] = {
                    "remaining": float("inf"),
                    "expires_at": None,
                    "next_tick_at": None,
                    "external": True,
                }
            return {
                "current_hp": self.current_hp,
                "maximum_hp": self.maximum_hp,
                "hp_ratio": max(0.0, min(1.0, self.current_hp / self.maximum_hp)),
                "hp_stage": self.hp_stage,
                "combat_enabled": self.combat_enabled,
                "is_ko": self.current_hp <= 0,
                "critical_hp": 0 < self.current_hp <= round(self.maximum_hp * self.critical_hp_percent),
                "invulnerable": t < self.invulnerable_until,
                "blocking": t < self.blocked_until,
                "statuses": active,
                "magic_locked": "silence" in active,
                "movement_locked": "freeze" in active or "bind" in active,
            }

    def set_combat_enabled(self, enabled: bool) -> EventResult:
        with self._lock:
            before = self.current_hp
            self.combat_enabled = bool(enabled)
            cleared = []
            if not self.combat_enabled and self.clear_statuses_when_disabled:
                cleared = sorted(set(self.statuses) | set(self.external_statuses))
                self.statuses.clear()
                self.external_statuses.clear()
                self.invulnerable_until = 0.0
                self.blocked_until = 0.0
            suffix = f" Cleared: {', '.join(cleared)}." if cleared else ""
            return EventResult(True, "combat_toggle", f"RP combat {'enabled' if self.combat_enabled else 'disabled'}.{suffix}", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)

    def record_block(self, window_seconds: float, now: float | None = None) -> EventResult:
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            before = self.current_hp
            if not self.combat_enabled:
                return EventResult(False, "block_ignored", "Block ignored: RP combat is disabled.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            self.blocked_until = max(self.blocked_until, t + max(0.0, float(window_seconds)))
            return EventResult(True, "blocked", "Block window opened.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES["blocked"])

    def apply_hit(self, hit_type: str, *, now: float | None = None, blocked: bool = False, bypass_iframes: bool = False) -> EventResult:
        hit = str(hit_type).strip().lower()
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            before = self.current_hp
            if hit not in self.damage_values:
                return EventResult(False, "hit_ignored", f"Unknown hit type: {hit_type}", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            if not self.combat_enabled:
                return EventResult(False, "hit_ignored", f"{hit.title()} hit ignored: RP combat is disabled.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            if before <= 0:
                return EventResult(False, "hit_ignored", f"{hit.title()} hit ignored: already KO.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            if blocked:
                return EventResult(True, "blocked", f"{hit.title()} attack blocked.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES["blocked"], metadata={"hit_type": hit})
            if not bypass_iframes and t < self.invulnerable_until:
                return EventResult(False, "hit_ignored", f"{hit.title()} hit ignored: invulnerable for {self.invulnerable_until - t:.2f}s.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            damage = self.damage_values[hit]
            self.current_hp = max(0, before - damage)
            if damage > 0:
                self.invulnerable_until = t + self.invulnerability_seconds
            return EventResult(True, "damage", f"{hit.title()} hit: -{damage} HP ({self.current_hp}/{self.maximum_hp}).", amount=damage, hp_before=before, hp_after=self.current_hp, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES[hit], metadata={"hit_type": hit})

    def apply_status(self, name: str, *, now: float | None = None) -> EventResult:
        key = str(name).strip().lower()
        t = time.monotonic() if now is None else float(now)
        with self._lock:
            before = self.current_hp
            if key not in self.status_rules:
                return EventResult(False, "status_ignored", f"Unknown status: {name}", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            if not self.combat_enabled:
                return EventResult(False, "status_ignored", f"{key.title()} ignored: RP combat is disabled.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            if before <= 0:
                return EventResult(False, "status_ignored", f"{key.title()} ignored: already KO.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            rule = self.status_rules[key]
            duration = max(0.1, float(rule.get("duration_seconds", 5.0)))
            tick_seconds = rule.get("tick_seconds")
            tick = max(0.1, float(tick_seconds)) if tick_seconds is not None else None
            tick_damage = max(0, int(rule.get("damage", 0)))
            existing = self.statuses.get(key)
            self.statuses[key] = ActiveStatus(
                name=key,
                expires_at=t + duration,
                next_tick_at=(existing.next_tick_at if existing and existing.next_tick_at and existing.next_tick_at > t else (t + tick if tick else None)),
                tick_seconds=tick,
                tick_damage=tick_damage,
            )
            return EventResult(True, "status_applied", f"{key.title()} applied for {duration:.1f}s.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp, metadata={"status": key})


    def set_external_status(self, name: str, active: bool, *, now: float | None = None) -> EventResult:
        """Mirror a persistent status owned by an existing avatar controller.

        This is deliberately separate from apply_status(): SHR00M already owns
        its Burn/Bleed timers and damage, so the desktop program must not apply
        a second DOT tick merely because the status parameter is visible over
        OSC.
        """
        key = str(name).strip().lower()
        with self._lock:
            before = self.current_hp
            if active:
                changed = key not in self.external_statuses
                self.external_statuses.add(key)
                message = f"Observed external {key.title()} active."
                event = "external_status_active"
            else:
                changed = key in self.external_statuses
                self.external_statuses.discard(key)
                message = f"Observed external {key.title()} cleared."
                event = "external_status_cleared"
            return EventResult(
                changed,
                event,
                message,
                hp_before=before,
                hp_after=before,
                maximum_hp=self.maximum_hp,
                metadata={"status": key, "external": True},
            )

    def clear_status(self, name: str) -> EventResult:
        key = str(name).strip().lower()
        with self._lock:
            before = self.current_hp
            removed = key in self.statuses or key in self.external_statuses
            self.statuses.pop(key, None)
            self.external_statuses.discard(key)
            return EventResult(
                removed,
                "status_cleared" if removed else "status_ignored",
                f"{key.title()} cleared." if removed else f"{key.title()} was not active.",
                hp_before=before,
                hp_after=before,
                maximum_hp=self.maximum_hp,
                metadata={"status": key},
            )

    def clear_statuses(self) -> EventResult:
        with self._lock:
            before = self.current_hp
            names = sorted(set(self.statuses) | set(self.external_statuses))
            self.statuses.clear()
            self.external_statuses.clear()
            return EventResult(True, "statuses_cleared", "Cleared statuses." if names else "No active statuses.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp, metadata={"statuses": names})

    def heal(self, amount: int) -> EventResult:
        with self._lock:
            before = self.current_hp
            if before <= 0:
                return EventResult(False, "heal_ignored", "Healing ignored: use Revive while KO.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            self.current_hp = min(self.maximum_hp, before + max(0, int(amount)))
            actual = self.current_hp - before
            return EventResult(actual > 0, "healing" if actual > 0 else "heal_ignored", f"Healed +{actual} HP ({self.current_hp}/{self.maximum_hp})." if actual > 0 else "HP is already full.", amount=actual, hp_before=before, hp_after=self.current_hp, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES["healing"])

    def full_heal(self) -> EventResult:
        with self._lock:
            before = self.current_hp
            if before <= 0:
                return EventResult(False, "heal_ignored", "Full Heal ignored: use Revive while KO.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            self.current_hp = self.maximum_hp
            return EventResult(self.current_hp != before, "healing" if self.current_hp != before else "heal_ignored", f"HP fully restored ({self.current_hp}/{self.maximum_hp}).", amount=self.current_hp - before, hp_before=before, hp_after=self.current_hp, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES["healing"])

    def revive(self, percent: float = 0.25) -> EventResult:
        with self._lock:
            before = self.current_hp
            if before > 0:
                return EventResult(False, "revive_ignored", "Revive ignored: character is not KO.", hp_before=before, hp_after=before, maximum_hp=self.maximum_hp)
            self.current_hp = max(1, round(self.maximum_hp * max(0.01, min(1.0, float(percent)))))
            self.statuses.clear()
            self.external_statuses.clear()
            self.invulnerable_until = time.monotonic() + self.invulnerability_seconds
            return EventResult(True, "revive", f"Revived with {self.current_hp}/{self.maximum_hp} HP.", amount=self.current_hp, hp_before=before, hp_after=self.current_hp, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES["healing"])

    def set_hp(self, hp: int) -> EventResult:
        with self._lock:
            before = self.current_hp
            self.current_hp = max(0, min(self.maximum_hp, int(hp)))
            return EventResult(True, "set_hp", f"HP set to {self.current_hp}/{self.maximum_hp}.", amount=self.current_hp - before, hp_before=before, hp_after=self.current_hp, maximum_hp=self.maximum_hp)

    def reconfigure(self, *, maximum_hp: int, damage_values: dict[str, int], invulnerability_seconds: float, critical_hp_percent: float, status_rules: dict[str, dict[str, Any]], preserve_ratio: bool = True) -> None:
        with self._lock:
            old_max = self.maximum_hp
            old_hp = self.current_hp
            self.maximum_hp = max(1, int(maximum_hp))
            if preserve_ratio and old_max > 0:
                self.current_hp = max(0, min(self.maximum_hp, round(old_hp / old_max * self.maximum_hp)))
            else:
                self.current_hp = min(self.current_hp, self.maximum_hp)
            for key in self.damage_values:
                self.damage_values[key] = max(0, int(damage_values.get(key, self.damage_values[key])))
            self.invulnerability_seconds = max(0.0, float(invulnerability_seconds))
            self.critical_hp_percent = max(0.01, min(0.99, float(critical_hp_percent)))
            self.status_rules = status_rules

    def tick(self, now: float | None = None) -> list[EventResult]:
        t = time.monotonic() if now is None else float(now)
        events: list[EventResult] = []
        with self._lock:
            for key in list(self.statuses):
                status = self.statuses.get(key)
                if status is None:
                    continue
                if status.expires_at <= t:
                    self.statuses.pop(key, None)
                    events.append(EventResult(True, "status_expired", f"{key.title()} expired.", hp_before=self.current_hp, hp_after=self.current_hp, maximum_hp=self.maximum_hp, metadata={"status": key}))
                    continue
                if status.next_tick_at is not None and status.tick_seconds is not None and status.next_tick_at <= t:
                    while status.next_tick_at is not None and status.next_tick_at <= t and status.next_tick_at < status.expires_at:
                        before = self.current_hp
                        if before <= 0:
                            break
                        self.current_hp = max(0, before - status.tick_damage)
                        events.append(EventResult(True, "dot_damage", f"{key.title()} tick: -{status.tick_damage} HP ({self.current_hp}/{self.maximum_hp}).", amount=status.tick_damage, hp_before=before, hp_after=self.current_hp, maximum_hp=self.maximum_hp, reaction_code=self.REACTION_CODES.get(key, 0), metadata={"status": key}))
                        status.next_tick_at += status.tick_seconds
                        if self.current_hp <= 0:
                            break
        return events
