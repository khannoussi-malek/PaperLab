import random
import time
import uuid

from app.core.screening_rank import Doc, StopHint, rank, stop_hint, tokens


def _doc(text, label=None):
    return Doc(id=uuid.uuid4(), text=text, label=label)


def test_tokens_lowercase_drops_stop_words_and_single_characters():
    assert tokens("The RCT of Sleep, a 2x trial") == ["rct", "sleep", "2x", "trial"]


def test_untrained_without_both_kinds_of_decision_keeps_found_order():
    docs = [_doc("sleep trial", True), _doc("a"), _doc("b")]
    assert rank(docs) == ([docs[1].id, docs[2].id], False)


def test_hit_sharing_words_with_positives_ranks_first():
    docs = [
        _doc("randomised controlled trial of sleep deprivation in adults", True),
        _doc("a survey of graph neural networks for molecules", False),
        _doc("graph neural network benchmark for molecules"),  # found first, looks negative
        _doc("sleep deprivation randomised trial in older adults"),  # looks positive
    ]
    ids, trained = rank(docs)
    assert trained is True
    assert ids == [docs[3].id, docs[2].id]


def test_maybe_counts_as_positive_by_label_true():
    docs = [_doc("sleep memory", True), _doc("protein folding", False), _doc("protein structure"), _doc("sleep study")]
    assert rank(docs)[0][0] == docs[3].id


def test_equal_scores_keep_found_order_and_empty_text_is_fine():
    docs = [_doc("sleep", True), _doc("protein", False), _doc(""), _doc("")]
    assert rank(docs) == ([docs[2].id, docs[3].id], True)


def test_stop_hint_counts_not_relevant_until_the_first_other_decision():
    assert stop_hint(["not_relevant", "not_relevant", "maybe", "not_relevant"], 100, True) == StopHint(2, 50, False)


def test_stop_hint_threshold_is_seven_percent_of_pool_at_least_fifty():
    assert stop_hint([], 3000, True).threshold == 210  # float ceil(0.07 * 3000) would give 211
    assert stop_hint([], 3001, True).threshold == 211
    assert stop_hint([], 10, True).threshold == 50


def test_stop_hint_shows_only_when_trained():
    streak = ["not_relevant"] * 50
    assert stop_hint(streak, 100, True).show is True
    assert stop_hint(streak, 100, False).show is False


def test_three_thousand_abstracts_rank_in_under_a_second():
    rng = random.Random(1)
    words = [f"w{i}" for i in range(20000)]
    docs = [
        _doc(" ".join(rng.choices(words, k=200)), True if i < 30 else False if i < 100 else None) for i in range(3000)
    ]
    start = time.perf_counter()
    rank(docs)
    assert time.perf_counter() - start < 1.0  # planning spike: ~0.45 s
