"""Streamed answer text -> speakable sentence chunks. Pure functions, no I/O.

The splitter judges a word only once whitespace after it has arrived, so a word split
across model tokens is never judged early.
"""

import re

FIRST_CHUNK_MIN_WORDS = 6
# ponytail: an "et al." that truly ends a sentence joins the next one. Fixing that needs a
# sentence model; this list covers the abbreviations research answers actually use.
PROTECTED = frozenset({"al.", "fig.", "eq.", "sec.", "vs.", "i.e.", "e.g.", "cf.", "pp.", "dr."})
_COMPLETE_WORD = re.compile(r"(\S+)\s")
_LAST_WORD = re.compile(r"(\S+)$")
_MARKER = re.compile(r"\s*\[[CN]\d+\]")
_MARKDOWN = re.compile(r"[*`#_]")
_SPOKEN = (
    (re.compile(r"\bet al\."), "et al"),
    (re.compile(r"\bFig\."), "Figure"),
    (re.compile(r"\bEq\."), "Equation"),
    (re.compile(r"\s*<\s*"), " less than "),
    (re.compile(r"%"), " percent"),
)


def _ends_chunk(word: str, words_so_far: int, is_first: bool) -> bool:
    w = word.lower()
    if w in PROTECTED:
        return False
    if w.endswith((".", "!", "?")):
        return True
    return is_first and words_so_far >= FIRST_CHUNK_MIN_WORDS and w.endswith((",", ";", ":"))


class SentenceSplitter:
    """Feed model tokens in order; each call returns the chunks that are now complete."""

    def __init__(self) -> None:
        self._pending = ""
        self._words: list[str] = []
        self._emitted = 0

    def feed(self, token: str) -> list[str]:
        self._pending += token
        return self._take_words(final=False)

    def flush(self) -> list[str]:
        out = self._take_words(final=True)
        if self._words:
            out.append(self._close())
        return out

    def _take_words(self, final: bool) -> list[str]:
        out: list[str] = []
        while True:
            head = self._pending.lstrip()
            match = _COMPLETE_WORD.match(head) or (_LAST_WORD.match(head) if final else None)
            if match is None:
                return out
            self._pending = head[match.end():]
            self._words.append(match.group(1))
            if _ends_chunk(match.group(1), len(self._words), self._emitted == 0):
                out.append(self._close())

    def _close(self) -> str:
        chunk = " ".join(self._words)
        self._words = []
        self._emitted += 1
        return chunk


def speakable(text: str) -> str:
    """Drop citation markers and markdown, and spell out symbols the voice would mangle."""
    text = _MARKER.sub("", text)
    text = _MARKDOWN.sub("", text)
    for pattern, replacement in _SPOKEN:
        text = pattern.sub(replacement, text)
    return " ".join(text.split())


def heard_text(chunks: list[tuple[str, float]], played_seconds: float) -> str:
    """Text the reader heard: whole chunks, then a word share of the chunk being cut off.

    Each chunk is (text, duration_seconds). The original text, markers included, is kept.
    """
    heard: list[str] = []
    remaining = played_seconds
    for text, duration in chunks:
        if remaining <= 0:
            break
        if remaining >= duration:
            heard.append(text)
            remaining -= duration
            continue
        share = int(len(text.split()) * remaining / duration)
        if share:
            heard.append(" ".join(text.split()[:share]))
        break
    return " ".join(heard)
