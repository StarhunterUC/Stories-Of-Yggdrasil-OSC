from stories_yggdrasil_osc.movement_lock import movement_locked_from_sam_state


def test_lock_only_confirmed_statuses():
    assert movement_locked_from_sam_state({"character": {"status_names": ["Freeze"]}})
    assert movement_locked_from_sam_state({"character": {"status_names": ["Bind"]}})
    assert movement_locked_from_sam_state({"character": {"status_names": ["Immobilize"]}})
    assert not movement_locked_from_sam_state({"character": {"status_names": ["Slow", "Haste"]}})


def test_missing_and_cleared_states_unlock():
    assert not movement_locked_from_sam_state(None)
    assert not movement_locked_from_sam_state({"character": {}})
    assert not movement_locked_from_sam_state({"character": {"status_names": []}})
    assert movement_locked_from_sam_state({"character": {"status_names": ["Freeze"], "status_effects": []}})
