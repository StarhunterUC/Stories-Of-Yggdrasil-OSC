from stories_yggdrasil_osc.ui_combat_effects import active_effect_labels, combat_stats_display


def test_all_effects_and_remaining_time_from_server():
    char = {"status_effects": [
        {"name": "Protect", "expires_at": 160},
        {"name": "Shell", "stacks": 2},
        {"name": "Haste"},
        {"name": "Old", "expires_at": 99},
    ], "status_names": ["Protect", "Shell", "Haste", "Bleed"]}
    labels = active_effect_labels(char, now=100)
    assert "Protect · 1m 0s" in labels
    assert "Shell · x2" in labels
    assert "Haste" in labels
    assert "Bleed" in labels
    assert all("Old" not in item for item in labels)


def test_no_local_status_leaks_into_remote_npc():
    assert active_effect_labels({"name": "Crow Demon", "status_names": ["Guard"]},
                                offline_statuses={"Burn": True}) == ["Guard"]
    assert active_effect_labels({}, offline_statuses={"Burn": True}) == ["Burn"]


def test_missing_stat_keys_are_not_presented_as_real_zeros():
    text, warning = combat_stats_display({"stats": {"ATK": 72}}, {}, [], "player")
    assert "ATK 72" in text
    assert "DEF —" in text
    assert not warning


def test_npc_stats_discrepancy_is_labeled_as_reference_only():
    roster = [{"name": "Crow Demon", "atk": 72, "def": 32, "mag": 45,
               "res": 30, "spd": 48, "eva": 6, "vit": 32}]
    effective = {"stats": {"ATK": 0, "DEF": 0, "MAG": 0, "RES": 0,
                           "SPD": 0, "EVA": 0, "VIT": 32}}
    text, warning = combat_stats_display(effective, {"name": "Crow Demon"}, roster, "npc")
    assert "ATK 72" in text and "DEF 32" in text
    assert "ROSTER REFERENCE ONLY" in warning
    assert not combat_stats_display(effective, {"name": "Crow Demon"}, roster, "player")[1]
