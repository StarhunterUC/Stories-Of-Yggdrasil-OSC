from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "pairing_code",
    "code",
}

ACTIVITY_GROUP_SECONDS = 20.0
ACTIVITY_CLEANUP_SUPPRESS_SECONDS = 45.0

# Encounter cleanup is sometimes published once per affected Sam.py object
# with a unique event ID. The Desktop should show the cleanup once, while
# preserving normal duplicate grouping for damage, healing, and errors.
_ACTIVITY_CLEANUP_SIGNATURES = {
    "libra was cleared because the encounter ended",
}


def _activity_message_signature(message: Any) -> str:
    text = re.sub(r"\s+", " ", str(message or "").strip()).casefold()
    return text.rstrip(".! ")


def should_suppress_activity_repeat(
    rows: Iterable[dict[str, Any]],
    category: str,
    message: str,
    *,
    now: float | None = None,
) -> bool:
    """Suppress repeated encounter-cleanup notices without hiding real events.

    Sam.py status events carry unique IDs, so the normal ID de-duplication cannot
    collapse multiple cleanup records created at the same encounter end. Only
    known non-actionable cleanup signatures are suppressed, and only briefly.
    """
    signature = _activity_message_signature(message)
    if signature not in _ACTIVITY_CLEANUP_SIGNATURES:
        return False

    wanted_category = str(category or "").strip().casefold()
    epoch = float(time.time() if now is None else now)

    for row in reversed(list(rows)[-100:]):
        updated = float(row.get("updated_epoch", row.get("epoch", 0.0)) or 0.0)
        age = epoch - updated
        if age > ACTIVITY_CLEANUP_SUPPRESS_SECONDS:
            break
        if (
            str(row.get("type") or "").strip().casefold() == wanted_category
            and _activity_message_signature(row.get("event")) == signature
        ):
            return True
    return False



def clamp_ui_scale(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = 1.0
    return max(0.8, min(1.6, round(parsed, 2)))


def safe_window_geometry(value: Any, fallback: str = "1220x760") -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{3,5}x\d{3,5}(?:[+-]\d{1,6}[+-]\d{1,6})?", text):
        width, height = text.split("x", 1)
        height = re.split(r"[+-]", height, maxsplit=1)[0]
        if int(width) >= 900 and int(height) >= 600:
            return text
    return fallback


def action_key(kind: Any, name: Any) -> str:
    return f"{str(kind or '').strip().casefold()}::{str(name or '').strip().casefold()}"


def _normalise_profile_row(row: Any, default_kind: str) -> dict[str, Any] | None:
    if isinstance(row, str):
        name = row.strip()
        if not name:
            return None
        return {"kind": default_kind, "name": name}
    if not isinstance(row, dict):
        return None
    name = str(row.get("name") or row.get("spell") or row.get("technick") or "").strip()
    if not name:
        return None
    result = dict(row)
    result.setdefault("kind", default_kind)
    result["name"] = name
    return result


def build_action_catalog(
    recovery_options: Iterable[dict[str, Any]],
    combat_profile: dict[str, Any] | None,
    *,
    current_mp: int = 0,
    favorites: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Build one searchable action catalog without inventing execution support.

    Recovery options are executable because the current Sam.py API exposes
    ``/recovery/use``. Magicks and Technicks are informational unless a future
    API explicitly exposes a Desktop execution command.
    """
    favorite_set = {str(value).strip().casefold() for value in favorites if str(value).strip()}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for option in recovery_options:
        if not isinstance(option, dict):
            continue
        kind = str(option.get("kind") or "Recovery").strip().title()
        name = str(option.get("name") or "").strip()
        if not name:
            continue
        key = action_key(kind, name)
        if key in seen:
            continue
        seen.add(key)
        available_raw = option.get("available", option.get("can_use", True))
        available_text = str(option.get("available_text") or "").strip()
        available = bool(available_raw)
        if available_text:
            available = available and available_text.casefold() not in {
                "no", "false", "unavailable", "0", "none",
            }
        reason = str(
            option.get("unavailable_reason")
            or option.get("reason")
            or ("Ready" if available else available_text or "Unavailable")
        ).strip()
        rows.append({
            "key": key,
            "favorite": key in favorite_set,
            "kind": kind,
            "name": name,
            "effect": str(option.get("effect_text") or option.get("description") or "").strip(),
            "cost": str(option.get("cost_text") or option.get("cost") or "—").strip(),
            "available": available,
            "status": "Ready" if available else "Unavailable",
            "reason": reason,
            "executable": True,
            "payload": dict(option),
        })

    profile = combat_profile if isinstance(combat_profile, dict) else {}
    blockers = [str(value).strip() for value in profile.get("casting_blockers", []) if str(value).strip()]

    for raw in profile.get("magicks", []) if isinstance(profile.get("magicks"), list) else []:
        row = _normalise_profile_row(raw, "Magick")
        if not row:
            continue
        kind = "Magick"
        name = row["name"]
        key = action_key(kind, name)
        if key in seen:
            continue
        seen.add(key)
        try:
            mp_cost = max(0, int(row.get("mp_cost", row.get("cost", 0)) or 0))
        except (TypeError, ValueError):
            mp_cost = 0
        local_blockers = list(blockers)
        if mp_cost > int(current_mp or 0):
            local_blockers.append(f"Needs {mp_cost} MP; current MP is {int(current_mp or 0)}")
        available = not local_blockers
        reason = "; ".join(dict.fromkeys(local_blockers)) if local_blockers else "Available through the VRChat action menu"
        rows.append({
            "key": key,
            "favorite": key in favorite_set,
            "kind": kind,
            "name": name,
            "effect": str(row.get("description") or row.get("target") or row.get("school") or "Authoritative Magick").strip(),
            "cost": f"{mp_cost} MP",
            "available": available,
            "status": "Available" if available else "Blocked",
            "reason": reason,
            "executable": False,
            "payload": row,
        })

    for raw in profile.get("technicks", []) if isinstance(profile.get("technicks"), list) else []:
        row = _normalise_profile_row(raw, "Technick")
        if not row:
            continue
        kind = "Technick"
        name = row["name"]
        key = action_key(kind, name)
        if key in seen:
            continue
        seen.add(key)
        unavailable = str(row.get("unavailable_reason") or "").strip()
        available = not unavailable
        rows.append({
            "key": key,
            "favorite": key in favorite_set,
            "kind": kind,
            "name": name,
            "effect": str(row.get("description") or row.get("target") or "Authoritative Technick").strip(),
            "cost": str(row.get("cost_text") or row.get("cost") or "—").strip(),
            "available": available,
            "status": "Available" if available else "Blocked",
            "reason": unavailable or "Available through the VRChat action menu",
            "executable": False,
            "payload": row,
        })

    rows.sort(key=lambda item: (not item["favorite"], item["kind"].casefold(), item["name"].casefold()))
    return rows


def filter_actions(
    rows: Iterable[dict[str, Any]],
    *,
    search: str = "",
    kind: str = "All",
    favorites_only: bool = False,
) -> list[dict[str, Any]]:
    needle = str(search or "").strip().casefold()
    wanted_kind = str(kind or "All").strip().casefold()
    output = []
    for row in rows:
        if favorites_only and not bool(row.get("favorite")):
            continue
        if wanted_kind not in {"", "all"} and str(row.get("kind") or "").casefold() != wanted_kind:
            continue
        haystack = " ".join(
            str(row.get(field) or "")
            for field in ("kind", "name", "effect", "cost", "status", "reason")
        ).casefold()
        if needle and needle not in haystack:
            continue
        output.append(dict(row))
    return output


def append_grouped_activity(
    rows: list[dict[str, Any]],
    category: str,
    message: str,
    *,
    now: float | None = None,
    max_rows: int = 500,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    epoch = float(time.time() if now is None else now)
    category = str(category)
    message = str(message)
    if rows:
        last = rows[-1]
        last_epoch = float(last.get("updated_epoch", last.get("epoch", 0.0)) or 0.0)
        if (
            str(last.get("type") or "") == category
            and str(last.get("event") or "") == message
            and epoch - last_epoch <= ACTIVITY_GROUP_SECONDS
        ):
            last["count"] = int(last.get("count", 1) or 1) + 1
            last["updated_epoch"] = epoch
            last["time"] = datetime.fromtimestamp(epoch).strftime("%H:%M:%S")
            return rows[-max_rows:], last
    row = {
        "time": datetime.fromtimestamp(epoch).strftime("%H:%M:%S"),
        "type": category,
        "event": message,
        "count": 1,
        "epoch": epoch,
        "updated_epoch": epoch,
    }
    rows.append(row)
    return rows[-max_rows:], row


def filter_activity(
    rows: Iterable[dict[str, Any]],
    *,
    category: str = "All",
    search: str = "",
) -> list[dict[str, Any]]:
    wanted = str(category or "All").strip().casefold()
    needle = str(search or "").strip().casefold()
    output = []
    for row in rows:
        row_type = str(row.get("type") or "")
        if wanted not in {"", "all"} and row_type.casefold() != wanted:
            continue
        haystack = f"{row_type} {row.get('event', '')}".casefold()
        if needle and needle not in haystack:
            continue
        output.append(dict(row))
    return output


def filter_npcs(
    rows: Iterable[dict[str, Any]],
    *,
    search: str = "",
    favorites: Iterable[str] = (),
    favorites_only: bool = False,
) -> list[dict[str, Any]]:
    favorite_set = {str(value).strip().casefold() for value in favorites if str(value).strip()}
    needle = str(search or "").strip().casefold()
    output = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        is_favorite = name.casefold() in favorite_set
        if favorites_only and not is_favorite:
            continue
        haystack = " ".join(
            str(row.get(field) or "")
            for field in ("name", "key", "type", "region", "level", "weaknesses", "resistances")
        ).casefold()
        if needle and needle not in haystack:
            continue
        item = dict(row)
        item["favorite"] = is_favorite
        output.append(item)
    output.sort(key=lambda item: (not item.get("favorite", False), str(item.get("name") or "").casefold()))
    return output


def redact_sensitive(value: Any, *, key_hint: str = "") -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.casefold() in SENSITIVE_KEYS or any(token in key_text.casefold() for token in ("token", "secret", "password", "authorization")):
                result[key_text] = "<redacted>" if item else ""
            else:
                result[key_text] = redact_sensitive(item, key_hint=key_text)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item, key_hint=key_hint) for item in value]
    if isinstance(value, str):
        text = value
        text = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1<redacted>", text)
        text = re.sub(r"\b\d{15,22}\b", "<discord-id>", text)
        return text
    return value


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def create_support_bundle(
    destination_dir: Path,
    *,
    config: dict[str, Any],
    runtime_state: dict[str, Any],
    event_rows: Iterable[dict[str, Any]],
    diagnostics: dict[str, Any],
    version: str,
    install_dir: Path,
    log_path: Path | None = None,
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = destination_dir / f"Stories_OSC_Support_Bundle_{stamp}.zip"
    payloads = {
        "README.txt": (
            "Stories Of Yggdrasil OSC sanitized support bundle\n"
            f"Created: {datetime.now(timezone.utc).isoformat()}\n"
            f"Desktop version: {version}\n"
            "Tokens, authorization secrets, pairing codes, and Discord IDs are redacted.\n"
        ),
        "settings.sanitized.json": json.dumps(redact_sensitive(deepcopy(config)), indent=2, ensure_ascii=False),
        "runtime_state.sanitized.json": json.dumps(redact_sensitive(deepcopy(runtime_state)), indent=2, ensure_ascii=False),
        "recent_activity.sanitized.json": json.dumps(redact_sensitive(list(event_rows)[-500:]), indent=2, ensure_ascii=False),
        "diagnostics.sanitized.json": json.dumps(redact_sensitive(deepcopy(diagnostics)), indent=2, ensure_ascii=False),
    }
    manifest = []
    for relative in ("version.json", "contracts/SPELL_ID_REGISTRY_v2.json", "contracts/TECHNICK_ID_REGISTRY_v1.json", "contracts/ITEM_ID_REGISTRY_v1.json"):
        path = install_dir / relative
        if path.is_file():
            manifest.append({"path": relative, "sha256": file_sha256(path), "size_bytes": path.stat().st_size})
    payloads["file_manifest.json"] = json.dumps(manifest, indent=2)
    if log_path and log_path.is_file():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
            payloads["events.sanitized.log"] = "\n".join(str(redact_sensitive(line)) for line in lines) + "\n"
        except Exception as exc:
            payloads["events.sanitized.log"] = f"Could not read event log: {type(exc).__name__}: {exc}\n"

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, text in payloads.items():
            zf.writestr(name, text)
    return archive
