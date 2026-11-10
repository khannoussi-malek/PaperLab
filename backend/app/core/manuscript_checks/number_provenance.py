"""P2: decimals and percents in the prose that no data file or table in the manuscript backs (S2P B4).

Ground truth is every number in the manuscript's .csv and .json files (plus the mean and sample std of each CSV
column, each JSON list and each key across a list of JSON objects) and every number inside a tabular. Silent when
there is neither.
Pure string work: no model, no network, never edits text."""

import csv
import io
import json
import math
import re
import statistics
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.core.manuscript_checks.base import Finding
from app.core.numbers import parse_number, tokens

NAME = "numbers.unbacked"
DATA_SUFFIXES = (".csv", ".json")
TABLES = re.compile(r"\\begin\{(tabular\*?|tabularx|tabulary|longtable\*?|tabu)\}(.*?)\\end\{\1\}", re.S)
TABLE_ARG = re.compile(r"\s*(?:\[[^\]]*\])?\s*\{(?:[^{}]|\{[^{}]*\})*\}")  # [pos]{spec}: p{2.5cm} is not a cell
WIDTH_FIRST = {"tabular*", "tabularx", "tabulary"}  # {width}{spec}


@dataclass(frozen=True)
class Truth:
    values: list[float]  # sorted absolute values
    labels: list[str]  # labels[i]: where values[i] came from
    problems: list[Finding]  # data files that could not be read


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _stats(nums: list[float], where: str) -> Iterator[tuple[float, str]]:
    if len(nums) >= 2:
        yield abs(statistics.fmean(nums)), f"mean of {where}"
        yield statistics.stdev(nums), f"std of {where}"  # sample std, ddof=1


def _from_text(text: str, where: str) -> Iterator[tuple[float, str]]:
    values = (abs(float(t)) for t in tokens(text))
    return ((v, where) for v in values if math.isfinite(v))  # a 400-digit token is inf; NaN would break bisect


def _csv(path: str, text: str) -> Iterator[tuple[float, str]]:
    rows = list(csv.reader(io.StringIO(text)))
    columns: dict[int, list[float]] = {}
    for row in rows:  # no row statistics: a row mixes unlike columns (seed, accuracy, loss)
        for c, cell in enumerate(row):
            yield from _from_text(cell, path)
            value = parse_number(cell).value
            if value is not None and math.isfinite(value):
                columns.setdefault(c, []).append(value)
    head = rows[0] if rows else []
    for c, nums in columns.items():
        name = head[c].strip() if c < len(head) and parse_number(head[c]).value is None else ""
        yield from _stats(nums, f"column {name or c + 1} in {path}")


def _json(path: str, text: str) -> Iterator[tuple[float, str]]:
    stack = [json.loads(text)]
    while stack:  # explicit stack: a deep file cannot blow the recursion limit here
        node = stack.pop()
        if _finite(node):
            yield abs(float(node)), path
        elif isinstance(node, str):
            yield from _from_text(node, path)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            yield from _stats([x for x in node if _finite(x)], f"a list in {path}")
            records = [x for x in node if isinstance(x, dict)]
            for key in sorted({k for rec in records for k in rec}):
                yield from _stats([rec[key] for rec in records if _finite(rec.get(key))], f"{key} in {path}")
            stack.extend(node)


def _cells(env: str, body: str) -> str:
    """A table body without its leading [pos], {width} and {spec} arguments."""
    for _ in range(2 if env in WIDTH_FIRST else 1):
        arg = TABLE_ARG.match(body)
        body = body[arg.end():] if arg else body
    return body


def harvest(files: Mapping[str, str], blanked: Mapping[str, str]) -> Truth | None:
    """Every number the manuscript's data backs, or None when it has no .csv/.json file and no number in a table.
    `blanked` maps each .tex path to its comment-blanked text."""
    data = [p for p in sorted(files) if p.lower().endswith(DATA_SUFFIXES)]
    pairs: list[tuple[float, str]] = []
    problems = []
    for path in data:
        read = _csv if path.lower().endswith(".csv") else _json
        try:
            pairs.extend(read(path, files[path]))
        except (csv.Error, ValueError, RecursionError, OverflowError) as exc:
            why = getattr(exc, "msg", None) or "not valid CSV or JSON"
            problems.append(Finding(NAME, "warning", path, getattr(exc, "lineno", None),
                                    f"{path} could not be read ({why}), so its numbers back nothing",
                                    "Fix the file; PaperLab only reads it."))
    for path, text in blanked.items():
        for m in TABLES.finditer(text):
            pairs.extend(_from_text(_cells(m.group(1), m.group(2)), f"a table in {path}"))
    if not data and not pairs:
        return None
    pairs.sort()
    return Truth([v for v, _ in pairs], [label for _, label in pairs], problems)
