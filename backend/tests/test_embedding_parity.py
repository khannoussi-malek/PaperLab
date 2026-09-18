"""Parity with the sentence-transformers model PaperLab ran before M23 (spec §4, §8.1). The fixture was recorded from
that model on 2026-09-18, before torch left, by the script in the M23 plan's Task 1.

The ONNX check needs the real full-precision model, so it is skipped unless MODELS_DIR holds it:
    MODELS_DIR="$HOME/.cache/paperlab-models" uv run pytest tests/test_embedding_parity.py -v
"""

import json
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.providers import embedding, search_model

FIXTURE = Path(__file__).parent / "fixtures" / "embedding_parity.json"
RECORDED = json.loads(FIXTURE.read_text())
# model.safetensors' LFS sha256 at the pinned commit e9b6763023c676ca8431644204f50c2b100d9aab
PINNED_WEIGHTS = "9e7d262b1fe5ea350782829496efa831901b77486bbde1cea54a4c822d010d5c"
FULL = search_model.VARIANTS["full"]
REAL_LOAD = embedding.load  # conftest's autouse fixture replaces it once each test starts


def test_the_fixture_holds_documents_and_queries_from_the_pinned_weights_as_unit_vectors():
    samples = RECORDED["samples"]
    assert (RECORDED["model"], RECORDED["weights_sha256"]) == ("nomic-ai/nomic-embed-text-v1.5", PINNED_WEIGHTS)
    assert {sample["kind"] for sample in samples} == {"document", "query"}
    assert len({sample["text"] for sample in samples}) == len(samples)
    for sample in samples:
        assert len(sample["vector"]) == 768
        assert abs(np.linalg.norm(sample["vector"]) - 1) < 1e-4  # normalize_embeddings=True


@pytest.mark.anyio
@pytest.mark.skipif(
    not search_model.present(settings.models_dir, FULL), reason="needs the full-precision model in MODELS_DIR"
)
async def test_full_precision_onnx_matches_the_sentence_transformers_vectors():
    model = REAL_LOAD(FULL)
    documents = [sample for sample in RECORDED["samples"] if sample["kind"] == "document"]
    queries = [sample for sample in RECORDED["samples"] if sample["kind"] == "query"]

    vectors = await embedding.embed_documents(model, [sample["text"] for sample in documents])
    vectors += [await embedding.embed_query(model, sample["text"]) for sample in queries]
    samples = documents + queries

    norms = [float(np.linalg.norm(got)) for got in vectors]
    cosines = [float(np.dot(got, sample["vector"])) / norm for got, sample, norm in zip(vectors, samples, norms)]
    assert min(cosines) >= 0.999, cosines
    assert max(abs(norm - 1) for norm in norms) < 1e-4, norms  # normalised, as the recorded vectors are
