import pytest

from contra.audio.types import PlaybackPosition
from contra.debate.conversation import ConversationState

DISPATCHED = (
    "Productivity gains are contested. "  # chars   0-33
    "Remote workers report higher output. "  # chars  33-70
    "But managers report lower collaboration."  # chars  70-110
)


def test_full_turn_records_everything_spoken():
    s = ConversationState()
    s.append_user_turn("Remote work is better.")
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    s.commit_agent_turn(h)
    msgs = s.messages()
    assert msgs[-1].role == "assistant"
    assert msgs[-1].content == DISPATCHED.strip()


def test_barge_in_truncates_history_to_spoken_audio():
    """FR-13: history records what was SPOKEN, not what was GENERATED."""
    s = ConversationState()
    s.append_user_turn("Remote work is better.")
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    # only the first chunk (sentence 1) fully played
    s.truncate_to_spoken(h, PlaybackPosition(1, 48_000, last_complete_span_end=33))
    content = s.messages()[-1].content
    assert content == "Productivity gains are contested."
    assert "Remote workers" not in content
    assert "managers" not in content


def test_barge_in_before_any_audio_played_records_nothing():
    s = ConversationState()
    s.append_user_turn("Go.")
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    s.truncate_to_spoken(h, PlaybackPosition(0, 0, last_complete_span_end=0))
    assert all(m.role != "assistant" for m in s.messages())


def test_truncation_rounds_back_to_word_boundary():
    s = ConversationState()
    h = s.begin_agent_turn()
    s.record_dispatched(h, "Remote workers report higher output.")
    # 27 lands mid-word inside "higher"
    s.truncate_to_spoken(h, PlaybackPosition(1, 100, last_complete_span_end=27))
    assert s.messages()[-1].content == "Remote workers report"


def test_generated_text_is_retained_separately_but_not_in_messages():
    s = ConversationState()
    h = s.begin_agent_turn()
    s.record_dispatched(h, DISPATCHED)
    s.truncate_to_spoken(h, PlaybackPosition(1, 48_000, 33))
    assert s.generated_text(h) == DISPATCHED
    assert s.messages()[-1].content == "Productivity gains are contested."


def test_invariant_i3_spoken_is_always_prefix_of_dispatched():
    """Invariant I-3, asserted directly."""
    s = ConversationState()
    for end in (0, 5, 33, 70, len(DISPATCHED)):
        h = s.begin_agent_turn()
        s.record_dispatched(h, DISPATCHED)
        s.truncate_to_spoken(h, PlaybackPosition(1, 1, end))
        spoken = next(
            (m.content for m in reversed(s.messages()) if m.role == "assistant"), ""
        )
        assert DISPATCHED.startswith(spoken.rstrip()), f"not a prefix at end={end}"
        assert len(spoken) <= max(end, 0)


def test_messages_alternate_after_system_block():
    """Invariant I-4."""
    s = ConversationState()
    s.set_system_prompt("You are a debate opponent.")
    for i in range(3):
        s.append_user_turn(f"user {i}")
        h = s.begin_agent_turn()
        s.record_dispatched(h, f"agent {i}")
        s.commit_agent_turn(h)
    roles = [m.role for m in s.messages()]
    assert roles == ["system"] + ["user", "assistant"] * 3


def test_double_commit_raises():
    s = ConversationState()
    h = s.begin_agent_turn()
    s.record_dispatched(h, "text")
    s.commit_agent_turn(h)
    with pytest.raises(ValueError):
        s.commit_agent_turn(h)


def test_unknown_handle_raises():
    from contra.debate.types import TurnHandle

    s = ConversationState()
    with pytest.raises(ValueError):
        s.record_dispatched(TurnHandle(index=99), "text")


def test_token_estimate_grows_with_history():
    s = ConversationState()
    before = s.token_estimate()
    s.append_user_turn("a fairly long user turn with several words in it")
    assert s.token_estimate() > before


def test_empty_user_turn_is_ignored():
    s = ConversationState()
    s.append_user_turn("   ")
    assert s.messages() == []
