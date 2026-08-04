from __future__ import annotations

import json
import zipfile
from pathlib import Path

from stories_yggdrasil_osc.qol import (
    action_key,
    append_grouped_activity,
    build_action_catalog,
    clamp_ui_scale,
    create_support_bundle,
    filter_actions,
    filter_activity,
    filter_npcs,
    redact_sensitive,
    safe_window_geometry,
    should_suppress_activity_repeat,
)


def test_ui_scale_and_geometry_are_bounded():
    assert clamp_ui_scale(99) == 1.6
    assert clamp_ui_scale(0.1) == 0.8
    assert safe_window_geometry("1300x800+10+20") == "1300x800+10+20"
    assert safe_window_geometry("20x20") == "1220x760"


def test_action_catalog_keeps_unavailable_magicks_visible_with_reason():
    rows = build_action_catalog(
        [{
            "kind": "Consumable",
            "name": "Potion",
            "effect_text": "Restore HP",
            "cost_text": "1 item",
            "available": True,
        }],
        {
            "casting_blockers": ["Silence"],
            "magicks": [{"name": "Cure", "mp_cost": 10, "description": "Restore HP"}],
            "technicks": ["Libra"],
        },
        current_mp=4,
        favorites=[action_key("Magick", "Cure")],
    )
    cure = next(row for row in rows if row["name"] == "Cure")
    assert cure["favorite"] is True
    assert cure["available"] is False
    assert "Silence" in cure["reason"]
    assert "Needs 10 MP" in cure["reason"]
    assert len(filter_actions(rows, search="cure")) == 1
    assert len(filter_actions(rows, favorites_only=True)) == 1


def test_activity_rows_group_and_filter_without_losing_count():
    rows = []
    rows, first = append_grouped_activity(rows, "ERROR", "Connection failed", now=100)
    rows, second = append_grouped_activity(rows, "ERROR", "Connection failed", now=110)
    assert first is second
    assert second["count"] == 2
    assert len(rows) == 1
    assert filter_activity(rows, category="ERROR", search="failed")[0]["count"] == 2


def test_npc_filter_prioritizes_favorites_and_searches_region():
    rows = [
        {"name": "Wolf", "region": "Milsante", "level": 5},
        {"name": "Bomb", "region": "Sandsea", "level": 7},
    ]
    filtered = filter_npcs(rows, search="sea", favorites=["Wolf"])
    assert [row["name"] for row in filtered] == ["Bomb"]
    all_rows = filter_npcs(rows, favorites=["Wolf"])
    assert all_rows[0]["name"] == "Wolf"


def test_support_bundle_redacts_tokens_and_discord_ids(tmp_path: Path):
    install = tmp_path / "install"
    install.mkdir()
    (install / "version.json").write_text('{"version":"0.8.14"}', encoding="utf-8")
    log = tmp_path / "events.log"
    log.write_text("Bearer abc123 user 215182141720363008", encoding="utf-8")
    archive = create_support_bundle(
        tmp_path,
        config={"sam": {"token": "secret-token"}},
        runtime_state={"owner_id": "215182141720363008"},
        event_rows=[{"event": "Discord 215182141720363008"}],
        diagnostics={"authorization": "Bearer abc123"},
        version="0.8.14",
        install_dir=install,
        log_path=log,
    )
    with zipfile.ZipFile(archive) as zf:
        settings = json.loads(zf.read("settings.sanitized.json"))
        runtime = zf.read("runtime_state.sanitized.json").decode()
        event_log = zf.read("events.sanitized.log").decode()
    assert settings["sam"]["token"] == "<redacted>"
    assert "215182141720363008" not in runtime
    assert "abc123" not in event_log
    assert "215182141720363008" not in event_log


def test_recursive_redaction_preserves_non_sensitive_values():
    value = redact_sensitive({"name": "Clover", "token": "abc", "nested": ["Bearer xyz"]})
    assert value["name"] == "Clover"
    assert value["token"] == "<redacted>"
    assert value["nested"] == ["Bearer <redacted>"]


def test_libra_encounter_cleanup_is_shown_once_per_cleanup_window():
    rows = []
    rows, first = append_grouped_activity(
        rows,
        "STATUS",
        "Libra was cleared because the encounter ended.",
        now=100,
    )
    assert first["count"] == 1
    assert should_suppress_activity_repeat(
        rows,
        "STATUS",
        "Libra was cleared because the encounter ended.",
        now=101,
    )
    assert should_suppress_activity_repeat(
        rows,
        "status",
        "  LIBRA was cleared because the encounter ended  ",
        now=120,
    )
    assert not should_suppress_activity_repeat(
        rows,
        "STATUS",
        "Libra was cleared because the encounter ended.",
        now=146,
    )


def test_normal_repeated_status_messages_still_group():
    rows = []
    rows, first = append_grouped_activity(rows, "STATUS", "Protect wore off.", now=100)
    assert not should_suppress_activity_repeat(
        rows,
        "STATUS",
        "Protect wore off.",
        now=101,
    )
    rows, second = append_grouped_activity(rows, "STATUS", "Protect wore off.", now=101)
    assert first is second
    assert second["count"] == 2
