"""Regenerates long-paper.pdf: twelve pages of one heading and one long paragraph each, about 30,000 characters of
text, so chat can't send it whole (SMALL_PAPER_CHARS is 24,000) and needs the search model.

Run with the backend environment (it has PyMuPDF):
  cd backend && uv run python ../frontend/e2e/fixtures/make_long_paper.py ../frontend/e2e/fixtures/long-paper.pdf
"""

import sys

import pymupdf

TOPICS = [
    "retrieval", "chunking", "embeddings", "highlights", "citations", "workspaces",
    "references", "enrichment", "evaluation", "notes", "charts", "graphs",
]
SENTENCES = [
    "This section of the long fixture paper discusses {topic} in enough words to fill most of a page.",
    "Every sentence is plain prose, so extraction keeps it as body text and chunking turns it into passages.",
    "A paper this long is never sent to chat whole: a question about {topic} has to be answered by search.",
    "Without the search model the paper is still ready, so it can be read, highlighted and noted as usual.",
    "The words differ from page to page, so each passage about {topic} is its own chunk with its own text.",
]

doc = pymupdf.open()
for number, topic in enumerate(TOPICS, start=1):
    body = " ".join(sentence.format(topic=topic) for sentence in SENTENCES * 5)
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 90), f"{number} On {topic}", fontsize=14, fontname="Times-Bold")
    page.insert_textbox(pymupdf.Rect(72, 110, 540, 740), body, fontsize=11, fontname="Times-Roman")
doc.set_metadata({"title": "PaperLab E2E Long Fixture"})
doc.save(sys.argv[1])
