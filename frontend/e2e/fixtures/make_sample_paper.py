"""Regenerates sample-paper.pdf: two pages, one heading and one paragraph each.

Run with the backend environment (it has PyMuPDF):
  cd backend && uv run python ../frontend/e2e/fixtures/make_sample_paper.py ../frontend/e2e/fixtures/sample-paper.pdf
"""

import sys

import pymupdf

INTRO = (
    "Highlights are the anchor for every note in PaperLab. A note keeps the exact page and "
    "region of the passage it came from, so a citation can always jump back to the source. "
    "This paragraph exists so the end-to-end test has real, selectable text to work with."
)
METHOD = (
    "The second page describes a method in enough words to form its own chunk. Coordinates are "
    "stored in PDF points with a top-left origin and converted to screen pixels only at render time."
)

doc = pymupdf.open()
for heading, body in [("1 Introduction", INTRO), ("2 Method", METHOD)]:
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 90), heading, fontsize=14, fontname="Times-Bold")
    page.insert_textbox(pymupdf.Rect(72, 110, 540, 300), body, fontsize=11, fontname="Times-Roman")
doc.set_metadata({"title": "PaperLab E2E Fixture"})
doc.save(sys.argv[1])
