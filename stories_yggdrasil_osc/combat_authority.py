from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


CONTACT_TIERS = {"weak", "average", "normal", "strong", "critical"}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _case(value: Any) -> str:
    return _clean(value).casefold()


def new_event_id(prefix: str = "contact") -> str:
    """Return a compact globally unique combat event identifier.

    The ID is generated once per Contact and must be reused unchanged if the
    HTTP request is retried so Sam.py can apply its idempotency cache.
    """
    return f"{prefix}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"


@dataclass
class CombatSourceHint:
    kind: str = ""
    avatar_id: str = ""
    vrchat_user_id: str = ""
    enemy_name: str = ""
    action_name: str = ""
    action_kind: str = ""
    element: str = ""
    received_at: float = 0.0
    source: str = ""

    def active(self, *, now: float | None = None, ttl_seconds: float = 2.0) -> bool:
        if not self.received_at:
            return False
        t = time.monotonic() if now is None else float(now)
        return (t - self.received_at) <= max(0.1, float(ttl_seconds))

    def clear(self) -> None:
        self.kind = ""
        self.avatar_id = ""
        self.vrchat_user_id = ""
        self.enemy_name = ""
        self.action_name = ""
        self.action_kind = ""
        self.element = ""
        self.received_at = 0.0
        self.source = ""


@dataclass
class CombatCatalog:
    api_version: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    enemies: list[dict[str, Any]] = field(default_factory=list)
    player_identity_bindings: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_player_avatar_ids: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def update(self, payload: dict[str, Any]) -> None:
        payload = payload if isinstance(payload, dict) else {}
        self.api_version = _clean(payload.get("api_version"))
        self.capabilities = dict(payload.get("capabilities") or {}) if isinstance(payload.get("capabilities"), dict) else {}
        self.enemies = [dict(row) for row in payload.get("enemies", []) if isinstance(row, dict)]
        self.player_identity_bindings = [
            dict(row) for row in payload.get("player_identity_bindings", []) if isinstance(row, dict)
        ]
        self.ambiguous_player_avatar_ids = [
            dict(row) for row in payload.get("ambiguous_player_avatar_ids", []) if isinstance(row, dict)
        ]
        self.warnings = [str(value) for value in payload.get("warnings", []) if str(value).strip()]

    def enemy(self, name: str) -> dict[str, Any] | None:
        wanted = _case(name)
        if not wanted:
            return None
        for row in self.enemies:
            if wanted in {_case(row.get("name")), _case(row.get("key"))}:
                return row
        return None

    def mapped_enemy_labels(self) -> list[str]:
        labels: list[str] = []
        for row in self.enemies:
            ids = [str(value).strip() for value in row.get("avatar_ids", []) if str(value).strip()]
            if not ids:
                continue
            name = _clean(row.get("name") or row.get("key"))
            if name:
                labels.append(name)
        return sorted(set(labels), key=str.casefold)

    @staticmethod
    def player_label(row: dict[str, Any]) -> str:
        name = _clean(row.get("char_name") or row.get("character") or row.get("name") or "Linked Player")
        vrc = _clean(row.get("vrchat_display_name"))
        uid = _clean(row.get("vrchat_user_id"))
        avatar = _clean(row.get("avatar_id"))
        detail = vrc or uid or avatar or _clean(row.get("user_id"))
        return f"{name} — {detail}" if detail else name

    def player_rows_by_label(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in self.player_identity_bindings:
            label = self.player_label(row)
            # Catalog rows are already de-duplicated server-side by linked
            # player/character. If two presentation labels collide, include a
            # stable suffix rather than silently replacing one identity.
            if label in out:
                suffix = _clean(row.get("user_id") or row.get("avatar_id") or row.get("vrchat_user_id"))
                label = f"{label} [{suffix}]" if suffix else f"{label} [duplicate]"
            out[label] = row
        return out


def _enemy_source_from_row(row: dict[str, Any], *, configured_avatar_id: str = "") -> tuple[dict[str, Any] | None, str]:
    avatar_ids = [str(value).strip() for value in row.get("avatar_ids", []) if str(value).strip()]
    requested = _clean(configured_avatar_id)
    if requested and requested in avatar_ids:
        avatar_id = requested
    elif avatar_ids:
        avatar_id = avatar_ids[0]
    else:
        return None, "The selected NPC has no bound Avatar ID in Sam.py."
    source = {
        "kind": "npc",
        "avatar_id": avatar_id,
        "enemy_name": _clean(row.get("name") or row.get("key")),
    }
    return source, ""


def build_incoming_contact_event(
    *,
    event_id: str,
    tier: str,
    source_enemy: bool,
    catalog: CombatCatalog,
    authority_config: dict[str, Any],
    hint: CombatSourceHint | None = None,
    now: float | None = None,
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    """Build a defender-reported incoming Contact for a Player target.

    Identity is deliberately conservative. The bridge never guesses a Player
    or NPC identity from a raw hit pulse. It uses a fresh external identity
    hint first, then an explicitly selected server-verified catalog identity.
    """
    tier_key = _case(tier)
    if tier_key not in CONTACT_TIERS:
        tier_key = "average"

    cfg = authority_config if isinstance(authority_config, dict) else {}
    hint_ttl = float(cfg.get("source_hint_ttl_seconds", 2.0) or 2.0)
    use_hint = hint is not None and hint.active(now=now, ttl_seconds=hint_ttl)
    metadata: dict[str, Any] = {"source_enemy": bool(source_enemy), "identity_source": ""}

    source: dict[str, Any]
    action_name = "Contact"
    action_kind = "physical"
    element = ""

    if source_enemy:
        if use_hint and _case(hint.kind) == "npc":
            if _clean(hint.avatar_id):
                source = {"kind": "npc", "avatar_id": _clean(hint.avatar_id)}
                if _clean(hint.enemy_name):
                    source["enemy_name"] = _clean(hint.enemy_name)
                metadata["identity_source"] = hint.source or "external_hint"
            elif _clean(hint.enemy_name):
                row = catalog.enemy(hint.enemy_name)
                if not row:
                    return None, f"NPC source hint '{hint.enemy_name}' is not in the current combat catalog.", metadata
                source, reason = _enemy_source_from_row(row)
                if source is None:
                    return None, reason, metadata
                metadata["identity_source"] = hint.source or "external_hint"
            else:
                return None, "NPC Contact was received without a usable NPC identity hint.", metadata
        else:
            selected = _clean(cfg.get("incoming_npc_enemy_name"))
            if not selected:
                return None, "NPC Contact is unattributed. Select an Incoming NPC Source or provide a verified source hint.", metadata
            row = catalog.enemy(selected)
            if not row:
                return None, f"Selected Incoming NPC Source '{selected}' is not in the current combat catalog.", metadata
            source, reason = _enemy_source_from_row(row, configured_avatar_id=_clean(cfg.get("incoming_npc_avatar_id")))
            if source is None:
                return None, reason, metadata
            metadata["identity_source"] = "selected_catalog_npc"
    else:
        if use_hint and _case(hint.kind) == "player" and (_clean(hint.vrchat_user_id) or _clean(hint.avatar_id)):
            source = {"kind": "player"}
            if _clean(hint.vrchat_user_id):
                source["vrchat_user_id"] = _clean(hint.vrchat_user_id)
            if _clean(hint.avatar_id):
                source["avatar_id"] = _clean(hint.avatar_id)
            metadata["identity_source"] = hint.source or "external_hint"
        else:
            vrc_user = _clean(cfg.get("pvp_source_vrchat_user_id"))
            avatar_id = _clean(cfg.get("pvp_source_avatar_id"))
            if not vrc_user and not avatar_id:
                return None, "Player Contact is unattributed. Select a verified PvP Source or provide a fresh identity hint.", metadata
            source = {"kind": "player"}
            if vrc_user:
                source["vrchat_user_id"] = vrc_user
            if avatar_id:
                source["avatar_id"] = avatar_id
            metadata["identity_source"] = "selected_verified_player"

    if use_hint:
        action_name = _clean(hint.action_name) or action_name
        hinted_kind = _case(hint.action_kind)
        if hinted_kind in {"physical", "magick", "healing"}:
            action_kind = hinted_kind
        element = _clean(hint.element)

    payload: dict[str, Any] = {
        "event_id": _clean(event_id),
        "source": source,
        "target": {"kind": "player"},
        "action": {
            "name": action_name,
            "kind": action_kind,
            "tier": tier_key,
        },
    }
    if element:
        payload["action"]["element"] = element
    return payload, "", metadata
