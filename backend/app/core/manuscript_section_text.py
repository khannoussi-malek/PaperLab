"""A manuscript file split into its top-level sections, each with a stable hash and a guessed role (M27e)."""

from dataclasses import dataclass
from pathlib import PurePosixPath

from app.core.manuscript_sections import _SECTION, END_MARKERS, input_lines
from app.core.manuscript_sentences import _blank_comments, _brace_end, claim_hash, to_plain
from app.core.sections import Role, assign_roles

MIN_BARE_WORDS = 20  # a file with no \section needs this much prose to count as one section


@dataclass(frozen=True)
class Slice:
    title: str
    start: int  # code points; the API converts to UTF-16
    end: int
    norm: str
    hash: str
    words: int
    guess: Role | None


def _guess(title: str) -> Role | None:
    role = assign_roles([title], {})[0].role
    return None if role in ("other", "back") else role


def _slice(blanked: str, title: str, start: int, end: int, guess: Role | None) -> Slice:
    raw = blanked[start:end]
    return Slice(title, start, end, " ".join(raw.split()), claim_hash(raw), len(to_plain(raw).split()), guess)


def section_slices(text: str, *, path: str, main_file: str) -> list[Slice]:
    blanked = _blank_comments(text)
    is_main = path == main_file
    if is_main and input_lines(blanked):
        return []  # its sections are their own files
    begin = blanked.find("\\begin{document}") if is_main else -1
    stop = min((i for k in END_MARKERS if (i := blanked.find(k, max(begin, 0))) >= 0), default=len(blanked))
    heads = [m for m in _SECTION.finditer(blanked, 0, stop)]
    if not heads:
        if len(to_plain(blanked[:stop]).split()) < MIN_BARE_WORDS:
            return []
        return [_slice(blanked, PurePosixPath(path).stem, 0, stop, None)]
    ends = [m.start() for m in heads[1:]] + [stop]
    out = []
    for i, (m, end) in enumerate(zip(heads, ends)):
        title = " ".join(blanked[m.end() : _brace_end(blanked, m.end() - 1) - 1].split())
        start = 0 if i == 0 and not is_main else m.start()
        out.append(_slice(blanked, title, start, end, _guess(title)))
    return out
