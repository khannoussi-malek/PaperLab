import math
from statistics import median

from pydantic import BaseModel

# How many turns a percentile needs before it is shown: fewer and it is just the largest value, not a percentile.
_MIN_TURNS = {"p90": 10, "p95": 20, "p99": 100}
_RANKS = {"p90": 0.90, "p95": 0.95, "p99": 0.99}


class Percentiles(BaseModel):
    n: int
    median: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None


def percentiles(values: list[int]) -> Percentiles:
    """Median and nearest-rank percentiles; a percentile is None until enough turns back it."""
    ordered = sorted(values)
    n = len(ordered)
    shown = {name: ordered[math.ceil(_RANKS[name] * n) - 1] for name, least in _MIN_TURNS.items() if n >= least}
    return Percentiles(n=n, median=median(ordered) if n else None, **shown)
