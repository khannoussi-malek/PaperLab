"""Parity with the sentence-transformers model PaperLab ran before M23 (spec §4, §8.1). The fixture was recorded from
that model on 2026-09-18, before torch left, by the script in the M23 plan's Task 1."""

import json
from pathlib import Path

import numpy as np

FIXTURE = Path(__file__).parent / "fixtures" / "embedding_parity.json"
RECORDED = json.loads(FIXTURE.read_text())
# model.safetensors' LFS sha256 at the pinned commit e9b6763023c676ca8431644204f50c2b100d9aab
PINNED_WEIGHTS = "9e7d262b1fe5ea350782829496efa831901b77486bbde1cea54a4c822d010d5c"


def test_the_fixture_holds_documents_and_queries_from_the_pinned_weights_as_unit_vectors():
    samples = RECORDED["samples"]
    assert (RECORDED["model"], RECORDED["weights_sha256"]) == ("nomic-ai/nomic-embed-text-v1.5", PINNED_WEIGHTS)
    assert {sample["kind"] for sample in samples} == {"document", "query"}
    assert len({sample["text"] for sample in samples}) == len(samples)
    for sample in samples:
        assert len(sample["vector"]) == 768
        assert abs(np.linalg.norm(sample["vector"]) - 1) < 1e-4  # normalize_embeddings=True
