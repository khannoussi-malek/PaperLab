"""Finding the cited claims in a note or answer: each sentence or table row and the papers it cites."""

import re
from dataclasses import dataclass

from app.core.chat import claim_text
from app.core.citations import citations

_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_SEE = re.compile(r"\(?\b[Ss]ee(?:\s+also)?\s+(?:the\s+)?\[\[[^\]]+\]\](?:\s*(?:,|and|or)\s*\[\[[^\]]+\]\])*\)?\.?")
# "… are in [[note]]." / "… is covered in [[note]]" at the end, or a "[[note]]: …" list item: it says where something is
# covered, not what a paper found (D278). Anything else with a wikilink is a claim.
_CROSS_REFERENCE = re.compile(
    r"\b(?:is|are)\s+(?:(?:covered|discussed|treated|described|summari[sz]ed|reviewed|listed)\s+)?in\s+"
    r"\[\[[^\]]+\]\]\s*\.?$|^\[\[[^\]]+\]\]\s*:"
)


@dataclass(frozen=True)
class Cited:
    claim: str  # what the paper is checked against, plain text
    citation: citations.Citation
    error: str | None = None  # not_a_claim


def _kept_name(c: citations.Citation) -> str:
    return c.text[: c.text.rindex("(")].rstrip()


def _without(sentence: str, found: list[citations.Citation], keep_names: bool = True) -> str:
    """The sentence with its citations cut out. A narrative citation ("Boden (2009) notes") leaves its names, so the
    sentence still reads as written (D277); a parenthesis goes whole. Overlapping spans become one cut."""
    spans = {(*c.span, _kept_name(c) if keep_names and c.narrative else "") for c in found}
    cuts: list[tuple[int, int, str]] = []
    for start, end, keep in sorted(spans):
        if cuts and start < cuts[-1][1]:
            cuts[-1] = (cuts[-1][0], max(cuts[-1][1], end), "")
        else:
            cuts.append((start, end, keep))
    for start, end, keep in reversed(cuts):
        sentence = sentence[:start] + keep + sentence[end:]
    return re.sub(r"\s+([.,;:!?])", r"\1", " ".join(sentence.split())).strip()


def _prose(text: str) -> str:
    """Drops "See [[note]]" pointers and turns other wikilinks into words."""
    text = _WIKILINK.sub(lambda m: m.group(2) or m.group(1).replace("-", " "), _SEE.sub("", text))
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", " ".join(text.split()))  # "et al." ending a sentence
    return re.sub(r"\s+([.,;:!?])", r"\1", text).strip()


def _row_claims(block: claim_text.Block) -> list[Cited]:
    """A table row's citation is checked against its own cell (the citation cut out), then against the row's cells
    that cite nothing, as prose. With two or more cited cells each gets only its own: another cited cell is another
    paper's finding."""
    cited_cells = sum(1 for cell in block.cells if citations.find(cell))
    uncited = [_prose(cell).rstrip(".") for cell in block.cells if not citations.find(cell)]
    out = []
    for cell in block.cells:
        if not (found := citations.find(cell)):
            continue
        bare = _without(cell, found, keep_names=False)
        own = _prose(_without(cell, found)).rstrip(".") if any(ch.isalnum() for ch in bare) else ""
        parts = [own] + ([] if cited_cells > 1 else uncited)
        claim = ". ".join(part for part in parts if part)
        if cited_cells > 1 and len(claim.split()) < 3:
            claim = ""
        out += [Cited(f"{claim}." if claim else "", c) for c in found if not c.superseded]
    return out


def _uncited_run(sentences: list[str]) -> list[str]:
    """The sentences up to the first one that carries its own citation."""
    run = []
    for sentence in sentences:
        if citations.find(sentence):
            break
        run.append(sentence)
    return run


def _block_claims(block: claim_text.Block) -> list[Cited]:
    """Each citation is checked against its own sentence (D277). Only a label the source marked (the block opens with
    a bold span that is that first sentence: "**Smith (2020).** …") hands its citation the rest of the block; a
    sentence that is only a citation otherwise has no claim. A cross-reference is not_a_claim."""
    sentences = citations.split_sentences(block.text)
    out = []
    for i, sentence in enumerate(sentences):
        if not (found := citations.find(sentence)):
            continue
        bare = _without(sentence, found, keep_names=False)
        if _CROSS_REFERENCE.search(bare):
            out += [Cited(_prose(_without(sentence, found)), c, "not_a_claim") for c in found if not c.superseded]
            continue
        if i == 0 and block.lead and sentence == block.lead:
            claim = _prose(" ".join(_uncited_run(sentences[1:])))
        elif not any(ch.isalnum() for ch in bare):  # nothing but the citation
            claim = ""
        else:
            claim = _prose(_without(sentence, found))
        if claim and claim[-1].isalnum():
            claim += "."
        out += [Cited(claim, c) for c in found if not c.superseded]
    return out


def cited_claims(body: str) -> list[Cited]:
    """Every citation in a note's body (markdown or plain text) with the claim it supports, in order (D276)."""
    return [c for b in claim_text.blocks(body) for c in (_row_claims(b) if b.cells else _block_claims(b))]
