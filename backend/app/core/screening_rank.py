"""Stage-1 screening order that learns from the reader's own decisions (M31a, D186).

ASReview's default model: TF-IDF features and multinomial naive Bayes, retrained from scratch on every call. Pure
and I/O-free; core/screening.py loads the rows and calls rank() and stop_hint().

Retrains per request (~0.45 s for 3,000 abstracts). The TF-IDF features are the slow part on a big pool (~10 s for
276k hits), so rank() takes them prebuilt from core/screening.py's per-workspace cache.
"""

import re
import uuid
from array import array
from collections import Counter
from dataclasses import dataclass

import numpy as np

# ASReview's tuned default for naive Bayes over TF-IDF (asreview.models.classifiers.NaiveBayesClassifier).
ALPHA = 3.822
# ASReview stopping-rule study (spec §3.2): this many not-relevant decisions in a row, as a share of the pool.
STOP_PERCENT = 7
STOP_MIN = 50
_WORD = re.compile(r"[a-z0-9]{2,}")
STOP_WORDS = frozenset(
    "the and for with that this from are was were been have has had not but its their our which these those "
    "into than then there such can may also each other more most some any all both between during over under "
    "using used use based via per we they them his her she he it is be as at by on in of to or an".split()
)  # fmt: skip


@dataclass(frozen=True)
class Doc:
    id: uuid.UUID
    text: str
    label: bool | None  # True: relevant or maybe; False: not relevant; None: unscreened


@dataclass(frozen=True)
class StopHint:
    streak: int
    threshold: int
    show: bool


def tokens(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.lower()) if word not in STOP_WORDS]


@dataclass(frozen=True)
class Features:
    """Sparse L2-normalised TF-IDF as three flat arrays (doc index, word index, weight) and the vocabulary size:
    3,000 abstracts over ~20k words would be a 60M-cell dense matrix, and each doc only has a few hundred words.
    int32/float32 keep a 276k-hit pool (~18M nonzeros) near 220 MB."""

    rows: np.ndarray
    cols: np.ndarray
    weights: np.ndarray
    vocabulary: int


def features(texts: list[str]) -> Features:
    vocabulary: dict[str, int] = {}
    rows, cols, tfs = array("i"), array("i"), array("f")  # compact while building: Python int lists cost ~36 B each
    for row, text in enumerate(texts):
        for word, tf in Counter(tokens(text)).items():
            rows.append(row)
            cols.append(vocabulary.setdefault(word, len(vocabulary)))
            tfs.append(tf)
    rows_a, cols_a = np.frombuffer(rows, dtype=np.int32), np.frombuffer(cols, dtype=np.int32)
    df = np.bincount(cols_a, minlength=len(vocabulary))
    weights = np.frombuffer(tfs, dtype=np.float32) * (np.log((1 + len(texts)) / (1 + df)) + 1)[cols_a]
    norms = np.sqrt(np.bincount(rows_a, weights=weights * weights, minlength=len(texts)))
    weights /= np.where(norms > 0, norms, 1.0)[rows_a]
    return Features(rows_a, cols_a, weights.astype(np.float32), len(vocabulary))


def rank(docs: list[Doc], prebuilt: Features | None = None) -> tuple[list[uuid.UUID], bool]:
    """The unscreened docs' ids, most likely relevant first, and whether a model was trained.

    `docs` come in found order ((first_seen_at, id)); ties and the untrained case keep it. Untrained until there is
    at least one positive and one negative decision. `prebuilt` is features() of the docs' texts in that same order;
    with it the docs' text is not read.
    """
    unscreened = [index for index, doc in enumerate(docs) if doc.label is None]
    labels = {doc.label for doc in docs}
    if True not in labels or False not in labels:
        return [docs[index].id for index in unscreened], False
    feats = prebuilt or features([doc.text for doc in docs])
    rows, cols, weights, vocabulary = feats.rows, feats.cols, feats.weights, feats.vocabulary
    delta = np.zeros(vocabulary)
    for label, sign in ((True, 1.0), (False, -1.0)):
        in_class = np.array([doc.label is label for doc in docs])[rows]
        totals = np.bincount(cols[in_class], weights=weights[in_class], minlength=vocabulary)
        # Multinomial naive Bayes, Laplace-smoothed with ASReview's alpha: log P(word | class).
        delta += sign * np.log((totals + ALPHA) / (totals.sum() + ALPHA * vocabulary))
    scores = np.bincount(rows, weights=weights * delta[cols], minlength=len(docs))
    # A stable sort, so equal scores keep found order.
    picked = np.array(unscreened, dtype=np.int64)
    return [docs[index].id for index in picked[np.argsort(-scores[picked], kind="stable")]], True


def stop_hint(recent_statuses: list[str], pool_size: int, trained: bool) -> StopHint:
    """`recent_statuses`: stage-1 decisions newest first (only those with a decided-at time)."""
    streak = 0
    for status in recent_statuses:
        if status != "not_relevant":
            break
        streak += 1
    # Integer ceiling: math.ceil(0.07 * 3000) is 211, since 0.07 * 3000 == 210.00000000000003.
    threshold = max(STOP_MIN, -(-pool_size * STOP_PERCENT // 100))
    return StopHint(streak=streak, threshold=threshold, show=trained and streak >= threshold)
