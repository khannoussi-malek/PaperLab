"""P2: decimals and percents in the prose that no data file or table in the manuscript backs (S2P B4).

Ground truth is every number in the manuscript's .csv and .json files (plus the mean and sample std of each CSV
column, each JSON list and each key across a list of JSON objects) and every number inside a tabular. Silent when
there is neither.
Pure string work: no model, no network, never edits text."""

import bisect
import csv
import io
import json
import math
import re
import statistics
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from app.core.manuscript_bib import CITE
from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_sentences import _blank_comments, _mask
from app.core.numbers import parse_number, tokens

NAME = "numbers.unbacked"
DATA_SUFFIXES = (".csv", ".json")
TABLES = re.compile(r"\\begin\{(tabular\*?|tabularx|tabulary|longtable\*?|tabu)\}(.*?)\\end\{\1\}", re.S)
TABLE_ARG = re.compile(r"\s*(?:\[[^\]]*\])?\s*\{(?:[^{}]|\{[^{}]*\})*\}")  # [pos]{spec}: p{2.5cm} is not a cell
WIDTH_FIRST = {"tabular*", "tabularx", "tabulary"}  # {width}{spec}
MAX_PER_FILE = 25  # calibration knob: a wrong data file would otherwise flood the panel
LINKS = re.compile(
    r"\\(?:[cC]ref|autoref|eqref|pageref|nameref|vref|url|href|doi|includegraphics)\*?"
    r"(?:\[[^\]]*\])?\{[^}]*\}"
)
CODE = re.compile(r"\\(?:verb|lstinline)\*?([^A-Za-z\s*]).*?\1|\\texttt\{[^{}]*\}")  # \verb|--alpha 0.5|
NUMBER = re.compile(
    r"(?<![\w.,\-/:=\[\\])"  # not glued to a word, a version, a range, a path, a key= or an [option]
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\w|[.,]\d)"  # not 3.5mm, 1.2.3, 2e-4
    r"(?P<pct>\s*(?:\\,\s*)?(?:\\%|percent\b)|\}\s*\{\\percent\})?"  # 91.3\%, 91.3\,\%, \SI{91.3}{\percent}
)
BRACED = re.compile(r"\\(?:num|SI|qty|textbf|textit|emph|underline)\{$")  # the only commands whose {arg} is prose
UNITS = (
    "ms ns us µs μs s sec secs seconds second min mins minutes minute h hrs hours hour days day Hz kHz MHz GHz "
    "dB dBm dBi nm µm μm mm cm m km mg g kg KB kB MB GB TB Kbps Mbps Gbps W mW kW V mV A mA mAh J kJ K "
    "°C °F ° px pixels fps FLOPs GFLOPs TFLOPs ppm rpm bits bytes Pa kPa MPa"
).split()  # calibration knob
UNIT = re.compile(
    r"(?:\s|\\[,; ])*(?:" + "|".join(sorted(map(re.escape, UNITS), key=len, reverse=True)) + r")(?![A-Za-z])|\}\s*\{\\"
)  # 3.5 ms, 3.5\,ms, \SI{3.5}{\milli\second}
CUE_WORDS = {  # a decimal right after one of these is a reference or a version, not a result
    "section",
    "sections",
    "sec",
    "secs",
    "chapter",
    "chapters",
    "chap",
    "figure",
    "figures",
    "fig",
    "figs",
    "table",
    "tables",
    "tab",
    "appendix",
    "eq",
    "eqs",
    "equation",
    "equations",
    "algorithm",
    "alg",
    "line",
    "lines",
    "step",
    "steps",
    "page",
    "pages",
    "p",
    "pp",
    "theorem",
    "thm",
    "lemma",
    "definition",
    "corollary",
    "proposition",
    "remark",
    "example",
    "part",
    "item",
    "version",
    "ver",
    "v",
    "release",
    "rev",
    "python",
    "pytorch",
    "torch",
    "tensorflow",
    "cuda",
    "cudnn",
    "ubuntu",
    "java",
    "node",
    "gcc",
    "numpy",
    "scipy",
    "sklearn",
    "jax",
    "macos",
    "ios",
    "android",
    "windows",
    "xgboost",
    "lightgbm",
    "catboost",
    "sqlite",
    "ros",
    "tensorrt",
    "onnx",
    "opencv",
    "keras",
    "matlab",
    "llama",
    "qwen",
    "mistral",
    "mixtral",
    "gemma",
    "phi",
    "gpt",
    "claude",
    "gemini",
    "falcon",
    "deepseek",
    "vicuna",  # calibration knob: products with versions
}
SECTION_SIGN = re.compile(r"(?:§|\\S)[\s~]*$")  # §4.2, § 4.2, \S~4.2
STAT_BEFORE = re.compile(
    # alpha and significance level: the operator is optional, "alpha level 0.05", "significance level of 0.01"
    r"(?:(?i:\balpha)(?:\s+level)?|α|\\alpha|(?i:\bsignificance\s+level))\$?\s*"
    r"(?:of\s+|(?:[=<>≤≥]|\\[lg]eq?\b)\s*)?\$?\s*$"
    # p = 0.03, p < 0.001: p needs its operator
    r"|\bp(?:-values?)?\$?\s*(?:[=<>≤≥]|\\[lg]eq?\b|\\text(?:less|greater)|of\b)\s*\$?\s*$"
)
CONFIDENCE_AFTER = re.compile(r"(?:\s|\\,)*(?:confidence|CI)\b")  # 95% confidence, 95% CI
CURRENCY = re.compile(r"[$€£]\s*$")  # $12.50, \$12.50 (the backslash is not adjacent to the digits)
RATIO_BEFORE = re.compile(r"/\s*$")  # the 0.1 in 0.8/0.1/0.1
RATIO_AFTER = re.compile(r"\s*/\s*\d")  # the 0.8 in 0.8/0.1/0.1
LAST_WORD = re.compile(r"([A-Za-z]+)\.?\s*\(?$")
HYPER = re.compile(
    r"learning[ -]rates?|\blr\b|dropout|batch[ -]sizes?|weight[ -]decay|\bdecay|\\?(?:var)?epsilon|ε"
    r"|momentum|\\beta|β|\\lambda|λ|temperature|label[ -]smoothing|warm[ -]?up|step[ -]sizes?"
    r"|\\?gamma|γ|discount[ -]factor|\bthreshold|top[ -]?p\b",
    re.I,
)
HYPER_AFTER = re.compile(r"\s+(?:sampling|learning|dropout)[ -]rates?\b", re.I)  # a 0.75 sampling rate
# The one list of difference cues: before the number, after any number, and after a percent only.
DIFF_BEFORE = re.compile(
    r"improve[sd]? by|improvements? (?:of|by)|gains? of|increase[sd]? (?:of|by)"
    r"|decrease[sd]? (?:of|by)|drop(?:s|ped)? (?:of|by)|reduce[sd]? by|higher than|lower than",
    re.I,
)
DIFF_AFTER = re.compile(r"(?:\s|\\,)*(?:percentage\s+points?|points?|pp)\b", re.I)  # 4.2 points, 1.5 pp
DIFF_AFTER_PERCENT = re.compile(r"(?:\s|\\,)*(?:increase|improvement|gain|drop)s?\b", re.I)  # a 12% gain
CONNECTORS = {
    "of",
    "to",
    "at",
    "is",
    "was",
    "were",
    "be",
    "set",
    "fixed",
    "equal",
    "equals",
    "and",
    "or",
    "a",
    "an",
    "the",
    "in",
    "from",
    "between",
    "initial",
    "initially",
    "rate",
    "with",
    "probability",
    "coefficient",
    "factor",
    "ratio",
    "schedule",
    "value",
    "parameter",
}
DIFF_CONNECTORS = CONNECTORS | {"about", "around", "roughly", "nearly", "almost", "up"}
CUE_WINDOW = 40  # characters before the number for hyperparameter and difference cues; calibration knob
SENTENCE_END = re.compile(
    r"(?<!\bal)(?<!\be\.g)(?<!\bi\.e)(?<!\bcf)(?<!\bvs)(?<!\bFig)(?<!\bEq)(?<!\bSec)[.!?]\s"
    r"|\n[ \t]*\n"
)  # "et al. " and "e.g. " do not end a sentence
SENTENCE_REACH = 600  # ponytail: a sentence is the text between ". " marks within this reach, not a real split


@dataclass(frozen=True)
class Truth:
    values: list[float]  # sorted absolute values
    labels: list[str]  # labels[i]: where values[i] came from
    problems: list[Finding]  # data files that could not be read


def _finite(x) -> bool:
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return False
    try:
        return math.isfinite(x)
    except OverflowError:  # a JSON integer beyond float range: skip this value, keep the file
        return False


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
        body = body[arg.end() :] if arg else body
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
            problems.append(
                Finding(
                    NAME,
                    "warning",
                    path,
                    getattr(exc, "lineno", None),
                    f"{path} could not be read ({why}), so its numbers back nothing",
                    "Fix the file; PaperLab only reads it.",
                )
            )
    for path, text in blanked.items():
        for m in TABLES.finditer(text):
            pairs.extend(_from_text(_cells(m.group(1), m.group(2)), f"a table in {path}"))
    if not data and not pairs:
        return None
    pairs.sort()
    return Truth([v for v, _ in pairs], [label for _, label in pairs], problems)


def prose(blanked: str) -> str:
    """Comment-blanked text with math, floats, tables, headings, captions, labels, refs, cites, links and code blanked.
    Same length as `blanked`, so offsets agree; count lines in `blanked`, never here."""
    chars = list(re.sub(r"[\0\1~]", " ", _mask(blanked)))
    for pattern in (TABLES, CITE, LINKS, CODE):
        for m in pattern.finditer(blanked):
            chars[m.start() : m.end()] = " " * (m.end() - m.start())
    return "".join(chars)


def _scales(value: float, percent: bool) -> tuple[float, ...]:
    """91.3% = 0.913 and 91.3 = 0.913; only a fraction below 1 is read as a percent (0.913 = 91.3), so prose 2.0
    is never backed by a 200 in the data."""
    if percent:
        return (1.0, 0.01)
    return (1.0, 0.01, 100.0) if value < 1 else (1.0, 0.01)


def _backed(truth: Truth, value: float, places: int, percent: bool) -> bool:
    """Equal after rounding the truth to the places the prose shows; either half-way direction counts."""
    for scale in _scales(value, percent):
        target, tol = value * scale, 0.5 * 10.0**-places * scale * (1 + 1e-9)
        i = bisect.bisect_left(truth.values, target - tol)
        if i < len(truth.values) and truth.values[i] <= target + tol:
            return True
    return False


def _nearest(truth: Truth, value: float, percent: bool) -> tuple[float, str]:
    best = None
    for scale in _scales(value, percent):
        target = value * scale
        i = bisect.bisect_left(truth.values, target)
        for j in (i - 1, i):
            if 0 <= j < len(truth.values):
                gap = abs(truth.values[j] - target) / max(target, 1e-12)
                if best is None or gap < best[0]:
                    best = (gap, truth.values[j], truth.labels[j])
    return best[1], best[2]


def _cued(cue: re.Pattern, blanked: str, start: int, connectors: set[str]) -> bool:
    """A cue in the short window before `start`, with only connector words between it and the number."""
    window = blanked[max(0, start - CUE_WINDOW) : start]
    cues = list(cue.finditer(window))
    return bool(cues) and set(re.findall(r"[A-Za-z]+", window[cues[-1].end() :].lower())) <= connectors


def _difference(scan: str, blanked: str, m: re.Match) -> bool:
    return (
        _cued(DIFF_BEFORE, blanked, m.start("num"), DIFF_CONNECTORS)
        or DIFF_AFTER.match(scan, m.end()) is not None
        or (m["pct"] is not None and DIFF_AFTER_PERCENT.match(scan, m.end()) is not None)
    )


def _excused(scan: str, blanked: str, m: re.Match) -> bool:
    start, end = m.start("num"), m.end()
    if start and scan[start - 1] == "{" and not BRACED.search(scan, max(0, start - 12), start):
        return True  # \linespread{1.3}, \scalebox{0.8}: layout, not a result
    if not m["pct"] and UNIT.match(scan, m.end("num")):
        return True
    word = LAST_WORD.search(scan, max(0, start - 30), start)
    if word and word[1].lower() in CUE_WORDS or SECTION_SIGN.search(blanked, max(0, start - 4), start):
        return True
    if STAT_BEFORE.search(blanked, max(0, start - 24), start):
        return True  # p = 0.03, p < 0.001, $\alpha$ = 0.05: significance, not a result (effect sizes stay checked)
    if m["pct"] and CONFIDENCE_AFTER.match(scan, m.end()):
        return True  # 95% confidence, 95\% CI
    if _cued(HYPER, blanked, start, CONNECTORS) or HYPER_AFTER.match(scan, end):
        return True
    if CURRENCY.search(scan, max(0, start - 4), start):
        return True  # $12.50 is money, not a result
    if RATIO_BEFORE.search(scan, max(0, start - 12), start) or RATIO_AFTER.match(scan, end):
        return True  # 0.8/0.1/0.1: a split, not a result
    ends = list(SENTENCE_END.finditer(blanked, max(0, start - SENTENCE_REACH), start))
    left = ends[-1].end() if ends else max(0, start - SENTENCE_REACH)
    right = SENTENCE_END.search(blanked, end)
    return CITE.search(blanked, left, right.start() if right else min(len(blanked), end + SENTENCE_REACH)) is not None


def _file(path: str, blanked: str, truth: Truth) -> list[Finding]:
    scan = prose(blanked)
    found = []
    for m in NUMBER.finditer(scan):
        num, percent = m["num"].replace(",", ""), m["pct"] is not None
        if "." not in num and not percent:
            continue  # bare integers are counts, years and constants
        value, places = float(num), len(num.partition(".")[2])
        if _backed(truth, value, places, percent) or _excused(scan, blanked, m):
            continue
        shown = m["num"] + ("%" if percent else "")
        near, label = _nearest(truth, value, percent)
        line = blanked.count("\n", 0, m.start()) + 1
        if _difference(scan, blanked, m):  # info: a computed gain is not in the data, so keep it out of the badge
            found.append(
                Finding(
                    NAME,
                    "info",
                    path,
                    line,
                    f'"{shown}" may be a computed difference; no data file or table has it',
                    f"Nearest data value: {near:.12g} ({label}). PaperLab does not compute differences, "
                    "so check this one by hand; PaperLab never edits your text.",
                )
            )
        else:
            found.append(
                Finding(
                    NAME,
                    "warning",
                    path,
                    line,
                    f'"{shown}" matches no number in the manuscript\'s data files or tables',
                    f"Nearest data value: {near:.12g} ({label}). Check the number, or add the file it "
                    "comes from; PaperLab never edits your text.",
                )
            )
    if len(found) > MAX_PER_FILE:
        rest = len(found) - MAX_PER_FILE
        found = found[:MAX_PER_FILE] + [
            Finding(
                NAME,
                "info",
                path,
                found[MAX_PER_FILE].line,
                f"{rest} more numbers in {path} match no data; only the first {MAX_PER_FILE} are listed",
                None,
            )
        ]
    return found


def _unbacked(ctx: CheckContext) -> list[Finding]:
    blanked = {p: _blank_comments(t) for p, t in sorted(ctx.files.items()) if p.endswith(".tex")}
    truth = harvest(ctx.files, blanked)
    if truth is None:
        return []
    if not truth.values:
        return truth.problems  # nothing to compare against: never flag prose against an empty set
    return truth.problems + [f for path, text in blanked.items() for f in _file(path, text, truth)]


CHECKS = (Check(NAME, "cheap", "Decimals and percents in the text that no data file or table backs", _unbacked),)
