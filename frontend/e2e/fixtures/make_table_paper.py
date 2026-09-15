"""Regenerates table-paper.pdf: one page with a captioned 3 x 3 table and a sentence holding "88.5 ± 0.3 F1".

Run with the backend environment (it has PyMuPDF):
  cd backend && uv run python ../frontend/e2e/fixtures/make_table_paper.py ../frontend/e2e/fixtures/table-paper.pdf
"""

import sys

import pymupdf

ROWS = [("System", "Dev F1", "Test F1"), ("BERT-B", "88.5", "87.0"), ("BERT-L", "90.9", "91.8")]
COLUMNS_X = (72, 220, 340)
SENTENCE = "Our best model reaches 88.5 ± 0.3 F1 on the dev set, and it trains in four days."

doc = pymupdf.open()
page = doc.new_page(width=612, height=792)
page.insert_text((72, 90), "1 Results", fontsize=14, fontname="Times-Bold")
page.insert_text((72, 130), "Table 1: Results on the dev set.", fontsize=10, fontname="Times-Roman")
for r, row in enumerate(ROWS):
    for x, text in zip(COLUMNS_X, row, strict=True):
        page.insert_text((x, 160 + 16 * r), text, fontsize=10, fontname="Times-Bold" if r == 0 else "Times-Roman")
# A Unicode font for "±": the base-14 Times has no glyph for it in PyMuPDF's default encoding.
page.insert_textbox(pymupdf.Rect(72, 260, 540, 320), SENTENCE, fontsize=11, fontname="helv")
doc.set_metadata({"title": "PaperLab Table Fixture"})
doc.save(sys.argv[1])
