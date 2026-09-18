"""Regenerates citation-paper.pdf: numbered citations linked (LINK_GOTO) to a two-column reference list.

Run with the backend environment (it has PyMuPDF):
  cd backend && uv run python ../frontend/e2e/fixtures/make_citation_paper.py ../frontend/e2e/fixtures/citation-paper.pdf
"""

import sys

import pymupdf

TITLE = "PaperLab Citation Fixture"
SIZE, LEAD = 9, 11  # the reference list's font size and line spacing
LEFT_X, RIGHT_X = 54, 316  # column starts; the gutter is 296-316
BODY = [
    "Fixtures cite fixtures [1] and a closed one [2], while [3] is one this",
    "library has never stored. A landing page [4] only looks free, and",
    "Figure 1 is a link that is not a citation. Plain [5] has no link.",
    "This fixture is 2 pages long.",
]
# [1] prints another title than the stored one, so only its DOI (broken at its hyphen) can match it.
# [2] straddles: its authors end the left column, its title opens the right one, above [3].
ENTRIES = {
    1: (LEFT_X, 180, ["Ada Fixture. 2026. PaperLab Fixture for Finding",
                      "Papers. Journal of Fixtures. doi:10.5555/paperlab-e2e-", "free"]),
    2: (LEFT_X, 729, ["Ada Fixture, Bea Placeholder, Cy Example, and", "Dee Sample. 2026."]),
    3: (RIGHT_X, 96, ["Some Author. 2019. A paper this library has", "never stored. Unknown Venue."]),
    4: (RIGHT_X, 122, ["Ada Fixture. 2026. PaperLab Landing Page Fixture.", "doi:10.5555/paperlab-e2e-landing"]),
}


def text(page, point, value, size=SIZE, bold=False):
    page.insert_text(point, value, fontsize=size, fontname="hebo" if bold else "helv")


doc = pymupdf.open()
body = doc.new_page(width=612, height=792)
text(body, (72, 72), TITLE, 18, bold=True)
for i, line in enumerate(BODY):
    text(body, (72, 120 + 16 * i), line, 11)

refs = doc.new_page(width=612, height=792)
text(refs, (54, 40), TITLE, 8)  # running header, left
text(refs, (430, 40), "Fixture Proceedings 2026", 8)  # running header, right: must not join [2]
text(refs, (54, 772), "2", 8)  # page number under [2]: must not end it early
text(refs, (54, 90), "5 Conclusion", 11, bold=True)
for i in range(3):
    text(refs, (54, 106 + LEAD * i), "Body prose in the left column before the list.")
text(refs, (54, 160), "References", 11, bold=True)
for label, (x, y, lines) in ENTRIES.items():
    text(refs, (x, y), f"[{label}]")
    for k, line in enumerate(lines):
        text(refs, (x + 16, y + LEAD * k), line)
text(refs, (RIGHT_X + 16, 70), "PaperLab Closed Access Fixture. Journal of")  # [2], continued
text(refs, (RIGHT_X + 16, 70 + LEAD), "Fixtures.")
text(refs, (RIGHT_X, 400), "Figure 1: A figure caption.")

body = doc[0]  # re-fetch: the proxy from before new_page() is stale


def link(rect, to):
    body.insert_link({"kind": pymupdf.LINK_GOTO, "from": rect, "page": 1, "to": pymupdf.Point(*to)})


for label, (x, y, _) in ENTRIES.items():
    r = body.search_for(f"[{label}]")[0]
    link(pymupdf.Rect(r.x0 + r.width / 4, r.y0, r.x1 - r.width / 4, r.y1), (x, y - LEAD))  # digits only, one line up
link(body.search_for("Figure 1")[0], (RIGHT_X, 390))
link(body.search_for("2 pages")[0], (0, 0))
doc.set_metadata({"title": TITLE})
doc.save(sys.argv[1])
