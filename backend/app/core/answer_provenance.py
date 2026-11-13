"""M33: the passages an answer cited, copied when it is saved (llm_outputs.source_snapshot).

A re-ingest replaces every chunk with a new one, so an answer's [C#] would point at nothing. The copy keeps each cited
passage's paper, page, section and text, so the citation still opens the right page, and the view can tell whether
the text is still in the paper.
"""

from app.core.retrieval import RetrievedChunk

MAX_SNAPSHOT_PASSAGES = 30
MAX_SNAPSHOT_CHARS = 2_000


def snapshot(chunks: list[RetrievedChunk], cited_labels: list[str]) -> list[dict]:
    """One entry per cited label, in label order: the first MAX_SNAPSHOT_PASSAGES of them, each text cut at
    MAX_SNAPSHOT_CHARS. `chunks[i]` is the passage labelled C{i+1}; a label outside `chunks` is skipped.
    """
    numbers = sorted({int(label[1:]) for label in cited_labels})
    entries = []
    for number in numbers:
        if not 1 <= number <= len(chunks) or len(entries) == MAX_SNAPSHOT_PASSAGES:
            continue
        chunk = chunks[number - 1]
        entries.append(
            {
                "label": f"C{number}",
                "paper_id": str(chunk.paper_id),
                "page": chunk.page,
                "section": chunk.section,
                "text": chunk.text[:MAX_SNAPSHOT_CHARS],
                "from_abstract": chunk.from_abstract,
            }
        )
    return entries
