from stories_yggdrasil_osc.sam_state_guard import stale_same_character_revision


def _state(rev, *, user="u1", character="Clover", mode="npc"):
    return {"revision": rev, "user_id": user, "linked_character": character, "profile_mode": mode}


def test_stale_revision_for_same_character_is_rejected():
    assert stale_same_character_revision(_state(40), _state(42))


def test_equal_or_newer_revisions_are_accepted():
    assert not stale_same_character_revision(_state(42), _state(42))
    assert not stale_same_character_revision(_state(43), _state(42))


def test_distinct_linked_character_is_not_rejected():
    assert not stale_same_character_revision(_state(1, character="Alexis"), _state(100, character="Clover"))


def test_distinct_user_is_not_rejected():
    assert not stale_same_character_revision(_state(1, user="u2"), _state(100, user="u1"))


def test_missing_revision_metadata_does_not_block_updates():
    assert not stale_same_character_revision({"character": {}}, _state(50))
