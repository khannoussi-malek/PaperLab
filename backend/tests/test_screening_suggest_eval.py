from evals.screening_suggest_eval import score


def _pairs(relevant_excluded, relevant_ok, not_relevant_excluded, not_relevant_other):
    return (
        [("relevant", "exclude")] * relevant_excluded + [("maybe", "include")] * relevant_ok
        + [("not_relevant", "exclude")] * not_relevant_excluded + [("not_relevant", "unsure")] * not_relevant_other
    )


def test_passes_at_five_percent_missed_on_enough_data():
    metrics = score(_pairs(1, 19, 60, 20), [1.0, 2.0, 3.0])
    assert (metrics.decided, metrics.positives, metrics.missed_relevant_rate) == (100, 20, 0.05)
    assert metrics.exclude_precision == 60 / 61
    assert metrics.unsure_share == 0.2
    assert metrics.median_seconds == 2.0
    assert metrics.passed is True


def test_fails_above_five_percent():
    assert score(_pairs(2, 18, 60, 20), [1.0]).passed is False


def test_fails_with_too_few_decisions_or_positives():
    assert score(_pairs(0, 20, 30, 20), [1.0]).passed is False  # 70 decided
    assert score(_pairs(0, 9, 60, 40), [1.0]).passed is False  # 9 positives
