"""Records `embedding_parity.json`: nomic-embed-text-v1.5 vectors for a fixed set of documents and queries, plus the
weights' sha256 and the sentence-transformers/torch versions that produced them, from today's (pre-M23)
`app.providers.embedding`. This is ground truth for `test_embedding_parity.py` and every later ONNX parity check.

Must run inside the `api` container, before M23 removes sentence-transformers and torch. Real command used for the
committed fixture (from the repo root):

    docker compose exec -T api python - < backend/tests/fixtures/record_embedding_parity.py \
        > backend/tests/fixtures/embedding_parity.json

The fixture this produces is recorded output, never hand-edited.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import sentence_transformers
import torch

from app.providers import embedding

CACHE = Path("/root/.cache/huggingface/hub/models--nomic-ai--nomic-embed-text-v1.5")
DOCUMENTS = [
    "Highlights are the anchor for every note in PaperLab.",
    "Self-attention relates every position of a sequence to every other position, so the representation of one "
    "token can draw on the whole input at once. We compute the attention weights from scaled dot products of "
    "queries and keys, apply a softmax, and use the result to average the values. Multi-head attention runs "
    "several of these in parallel on learned projections and concatenates their outputs.",
    "Our best model reaches 88.5 ± 0.3 F1 on the dev set (Table 2), a gain of 1.4 points over BERT-Large; we use "
    "α = 0.1, β₂ = 0.98 and a warm-up of 4,000 steps.",
    "[12] A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, and I. Polosukhin. "
    "Attention is all you need. In Advances in Neural Information Processing Systems, pages 5998–6008, 2017.",
    "Les résumés restent lisibles : l'élève naïve lit le cœur de l'article, puis ses références.",
    "Reading a research paper well takes more than one pass. The first pass is a quick scan of the title, the "
    "abstract, the introduction and the conclusions, to decide whether the paper is worth more time at all. The "
    "second pass reads the paper with greater care but skips the proofs, noting the key points, the figures and "
    "the references that look worth following. The third pass rebuilds the paper in the reader's own head: the "
    "reader takes the same assumptions as the authors and re-creates the work, comparing each step with the "
    "paper to find its hidden assumptions, its missing citations and the places where the experiments do not "
    "quite support the claims. A tool that helps with this keeps every note tied to the exact passage it came "
    "from, answers questions with citations that jump back to the page, and lets the reader compare what several "
    "papers say about one question without losing track of which paper said what. Search over the passages is "
    "what makes those answers possible when a paper is too long to read into a prompt in one go, and it is also "
    "what finds the two or three passages that matter among the hundreds a library of papers holds.",
]
QUERIES = [
    "What is the method?",
    "How does self-attention relate positions in a sequence?",
    "Which F1 score does the best model reach on the dev set?",
    "who wrote attention is all you need",
]


def weights_sha256() -> str:
    """sha256 of the model.safetensors sentence-transformers loaded (the cache's current snapshot)."""
    snapshot = CACHE / "snapshots" / (CACHE / "refs" / "main").read_text().strip()
    with (snapshot / "model.safetensors").open("rb") as weights:
        return hashlib.file_digest(weights, "sha256").hexdigest()


async def main() -> None:
    model = embedding.load()
    documents = await embedding.embed_documents(model, DOCUMENTS)
    queries = [await embedding.embed_query(model, query) for query in QUERIES]
    samples = [
        *({"kind": "document", "text": t, "vector": [round(x, 7) for x in v]} for t, v in zip(DOCUMENTS, documents)),
        *({"kind": "query", "text": t, "vector": [round(x, 7) for x in v]} for t, v in zip(QUERIES, queries)),
    ]
    json.dump(
        {
            "model": "nomic-ai/nomic-embed-text-v1.5",
            "weights_sha256": weights_sha256(),
            "recorded_with": f"sentence-transformers {sentence_transformers.__version__}, torch {torch.__version__}",
            "recorded": "2026-09-18",
            "samples": samples,
        },
        sys.stdout,
        ensure_ascii=False,
    )


asyncio.run(main())
