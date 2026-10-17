"""Zotero note HTML -> markdown (M40, D269). Converted, never rendered: only a handful of tags map to markdown, every
other tag is dropped and its text kept, script and style are dropped whole, and only http(s) and mailto links
survive."""

import re
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

HEADINGS = {"h1": "#", "h2": "##", "h3": "###"}
BLOCKS = {"p", "div", "ul", "ol", "br"}
DROPPED = {"script", "style"}
URL_SAFE = ":/?#@!$&'*+,;=%-._~"  # everything else, including ( ) < > [ ] and spaces, is percent-encoded
SAFE_SCHEMES = {"http", "https", "mailto"}
HAS_TAGS = re.compile(r"</?[a-zA-Z][^>]*>")


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[list[str]] = [[]]  # open containers (blockquote, li, heading, link) collect their own text
        self.kinds: list[tuple[str, str]] = []  # (tag, extra) for each container above the root
        self.lists: list[list[int]] = []  # [counter] for an ol, [0] marks a ul as [-1]
        self.skip = 0

    def _put(self, text: str) -> None:
        self.stack[-1].append(text)

    def _open(self, tag: str, extra: str = "") -> None:
        self.stack.append([])
        self.kinds.append((tag, extra))

    def _close(self, tag: str) -> None:
        if not self.kinds or self.kinds[-1][0] != tag:
            return  # a stray or mis-nested end tag
        _, extra = self.kinds.pop()
        text = "".join(self.stack.pop()).strip()
        if tag == "a":
            href = extra.strip()
            safe = urlsplit(href).scheme.lower() in SAFE_SCHEMES
            self._put(f"[{text}]({quote(href, safe=URL_SAFE)})" if text and href and safe else text)
        elif tag == "li":
            first = self.lists[-1] if self.lists else [-1]
            marker = "- " if first[0] < 0 else f"{first[0]}. "
            if first[0] >= 0:
                first[0] += 1
            self._put("\n" + marker + text.replace("\n", "\n  "))
        elif text and tag == "blockquote":
            self._put("\n\n" + "\n".join("> " + line for line in text.split("\n")) + "\n\n")
        elif text:
            self._put(f"\n\n{extra} {text}\n\n")  # a heading

    def handle_starttag(self, tag, attrs):
        if tag in DROPPED:
            self.skip += 1
        elif tag == "br":
            self._put("\n")
        elif tag in ("p", "div", "ul", "ol"):
            self._put("\n\n")
            if tag in ("ul", "ol"):
                self.lists.append([-1] if tag == "ul" else [1])
        elif tag in ("strong", "b"):
            self._put("**")
        elif tag in ("em", "i"):
            self._put("*")
        elif tag == "a":
            self._open("a", dict(attrs).get("href") or "")
        elif tag in ("li", "blockquote"):
            self._open(tag)
        elif tag in HEADINGS:
            self._open(tag, HEADINGS[tag])

    def handle_endtag(self, tag):
        if tag in DROPPED:
            self.skip = max(0, self.skip - 1)
        elif tag in ("p", "div"):
            self._put("\n\n")
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            self._put("\n\n")
        elif tag in ("strong", "b"):
            self._put("**")
        elif tag in ("em", "i"):
            self._put("*")
        elif tag in ("a", "li", "blockquote") or tag in HEADINGS:
            self._close(tag)

    def handle_data(self, data):
        if not self.skip:
            self._put(re.sub(r"\s+", " ", data))


# Note bodies are shown as plain text; any future markdown rendering of them must sanitise at render time.
def html_to_markdown(text: str) -> str:
    """Markdown for a Zotero note. Plain text (no tags) is returned as it is, trimmed."""
    if not HAS_TAGS.search(text):
        return text.strip()
    converter = _Converter()
    converter.feed(text)
    converter.close()
    while converter.kinds:  # unclosed containers: keep their text
        converter._close(converter.kinds[-1][0])
    out = "".join(converter.stack[0])
    out = re.sub(r"[ \t]*\n[ \t]*", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
