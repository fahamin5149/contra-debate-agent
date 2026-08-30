from contra.debate.segmenter import SentenceSegmenter


def feed_all(seg: SentenceSegmenter, text: str) -> list[str]:
    out: list[str] = []
    for ch in text:
        out.extend(seg.feed(ch))
    return out


def test_emits_on_terminal_punctuation_followed_by_space():
    seg = SentenceSegmenter()
    units = feed_all(seg, "Productivity gains are contested. Next one here.")
    assert units == ["Productivity gains are contested."]


def test_short_fragment_is_held_and_merged():
    """Kokoro ONNX is inefficient below ~15 chars (ADR-0006)."""
    seg = SentenceSegmenter()
    units = feed_all(seg, "Hi. That is a much longer sentence here. ")
    assert units == ["Hi. That is a much longer sentence here."]


def test_does_not_split_decimal_numbers():
    seg = SentenceSegmenter()
    units = feed_all(seg, "The figure is 13.5 percent of all workers. ")
    assert units == ["The figure is 13.5 percent of all workers."]


def test_emits_on_clause_break_when_buffer_is_long():
    seg = SentenceSegmenter()
    long_clause = "Remote workers consistently report far higher output levels, "
    units = feed_all(seg, long_clause + "but managers disagree with that entirely.")
    assert len(units) == 1
    assert units[0].endswith(",")


def test_force_emits_at_max_chars():
    seg = SentenceSegmenter(max_unit_chars=60)
    units = feed_all(seg, "word " * 40)
    assert units
    assert all(len(u) <= 60 for u in units)


def test_flush_emits_remainder():
    seg = SentenceSegmenter()
    feed_all(seg, "An unterminated trailing sentence")
    assert seg.flush() == ["An unterminated trailing sentence"]


def test_flush_is_idempotent():
    seg = SentenceSegmenter()
    feed_all(seg, "Something here")
    assert seg.flush() == ["Something here"]
    assert seg.flush() == []


def test_no_empty_units_ever_emitted():
    seg = SentenceSegmenter()
    units = feed_all(seg, "  .  ...   ") + seg.flush()
    assert all(u.strip() for u in units)
