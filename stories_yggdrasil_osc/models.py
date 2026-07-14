from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EventResult:
    accepted: bool
    event: str
    message: str
    amount: int = 0
    hp_before: int = 0
    hp_after: int = 0
    maximum_hp: int = 1
    reaction_code: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def hp_ratio(self) -> float:
        if self.maximum_hp <= 0:
            return 0.0
        return max(0.0, min(1.0, self.hp_after / self.maximum_hp))


@dataclass
class ActiveStatus:
    name: str
    expires_at: float
    next_tick_at: float | None = None
    tick_seconds: float | None = None
    tick_damage: int = 0

    def remaining(self, now: float) -> float:
        return max(0.0, self.expires_at - now)


@dataclass(frozen=True)
class PendingHit:
    hit_type: str
    due_at: float
    received_at: float
    source: str = "soy"
    external_health_owns_damage: bool = False
