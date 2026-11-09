"""P15: stock AI phrases ("it is worth noting") in prose; reads wording_lists.toml (S2P B2)."""

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_sentences import _blank_comments, _mask, in_range, split_sentences

LISTS = Path(__file__).with_name("wording_lists.toml")
DEFAULT_HINT = "Say it plainly or cut it; PaperLab never rewrites your text."
PROOF = re.compile(r"\\begin\{proof\}.*?\\end\{proof\}", re.S)


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern
    why: str
    severity: str
    hint: str
    skip_sentence: tuple[re.Pattern, ...] = ()
    skip_after: re.Pattern | None = None


@cache
def load_rules() -> dict[str, tuple[Rule, ...]]:
    data = tomllib.loads(LISTS.read_text(encoding="utf-8"))
    return {
        "ai_phrase": tuple(
            Rule(e["id"], re.compile(e["pattern"], re.I), e["why"], e.get("severity", "warning"), e.get("hint", DEFAULT_HINT))
            for e in data["ai_phrase"]
        ),
        "overclaim": tuple(
            Rule(
                e["id"], re.compile(e["pattern"], re.I), e["why"], e.get("severity", "warning"), e["hint"],
                tuple(re.compile(data["guards"][g], re.I) for g in e.get("skip_sentence_if", ())),
                re.compile(e["skip_after"], re.I) if "skip_after" in e else None,
            )
            for e in data["overclaim"]
        ),
    }


def prose(text: str) -> tuple[str, str]:
    """(comment-blanked text for line numbers, prose with comments, proofs, math, headings, floats and ~ blanked).
    Same length as `text`, so offsets agree."""
    blanked = _blank_comments(text)
    no_proof = PROOF.sub(lambda m: re.sub(r"[^\n]", " ", m.group()), blanked)
    return blanked, re.sub(r"[\0\1~]", " ", _mask(no_proof))


def _ai_phrase(ctx: CheckContext) -> list[Finding]:
    found = []
    for path in sorted(p for p in ctx.files if p.endswith(".tex")):
        blanked, text = prose(ctx.files[path])
        for rule in load_rules()["ai_phrase"]:
            for m in rule.pattern.finditer(text):
                shown = " ".join(m.group().split())
                found.append(Finding(
                    "wording.ai_phrase", rule.severity, path, blanked.count("\n", 0, m.start()) + 1,
                    f'"{shown}" reads like stock AI phrasing: {rule.why}', rule.hint,
                ))
    return sorted(found, key=lambda f: (f.file, f.line))


def _sentence(text: str, blanked: str, sentences: list, start: int, end: int) -> str:
    """The raw sentence holding [start, end); when the splitter dropped it (under 4 words), the text between the
    nearest sentence ends, so a neighbouring sentence never excuses this one."""
    hit = in_range(sentences, start, start)
    if hit:
        return hit[0].raw
    left = max(blanked.rfind(c, 0, start) for c in ".?!") + 1
    ends = [i for i in (blanked.find(c, end) for c in ".?!") if i >= 0]
    return blanked[left : min(ends) if ends else len(blanked)]


def _overclaim(ctx: CheckContext) -> list[Finding]:
    found = []
    for path in sorted(p for p in ctx.files if p.endswith(".tex")):
        text = ctx.files[path]
        blanked, scan = prose(text)
        sentences = None  # split lazily: most files never hit a guarded rule
        for rule in load_rules()["overclaim"]:
            for m in rule.pattern.finditer(scan):
                if rule.skip_after and rule.skip_after.match(scan, m.end()):
                    continue
                if rule.skip_sentence:
                    sentences = split_sentences(text) if sentences is None else sentences
                    raw = _sentence(text, blanked, sentences, m.start(), m.end())
                    if any(g.search(raw) for g in rule.skip_sentence):
                        continue
                shown = " ".join(m.group().split())
                found.append(Finding("wording.overclaim", rule.severity, path, blanked.count("\n", 0, m.start()) + 1,
                                     f'"{shown}" is a strong claim: {rule.why}', rule.hint))
    return sorted(found, key=lambda f: (f.file, f.line))


CHECKS = (
    Check("wording.ai_phrase", "cheap", 'Stock AI phrases such as "it is worth noting"', _ai_phrase),
    Check("wording.overclaim", "cheap", "Strong claim words that need evidence", _overclaim),
)
