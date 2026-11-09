"""P15: stock AI phrases ("it is worth noting") in prose; reads wording_lists.toml (S2P B2)."""

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.core.manuscript_checks.base import Check, CheckContext, Finding
from app.core.manuscript_sentences import _blank_comments, _mask

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


@cache
def load_rules() -> dict[str, tuple[Rule, ...]]:
    data = tomllib.loads(LISTS.read_text(encoding="utf-8"))
    return {
        "ai_phrase": tuple(
            Rule(e["id"], re.compile(e["pattern"], re.I), e["why"], e.get("severity", "warning"), e.get("hint", DEFAULT_HINT))
            for e in data["ai_phrase"]
        )
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


CHECKS = (Check("wording.ai_phrase", "cheap", 'Stock AI phrases such as "it is worth noting"', _ai_phrase),)
