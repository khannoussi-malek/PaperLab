"""The built-in search model's arithmetic, on a fake ONNX session and a tiny real tokenizer (D134, spec §8.2)."""

import numpy as np
from onnx_fakes import TABLE, FakeSession, expected_vector, ids, tiny_tokenizer

from app.providers import onnx_embedding
from app.providers.onnx_embedding import Embedder


def test_a_text_becomes_its_token_embeddings_averaged_at_unit_length():
    session = FakeSession()

    [vector] = Embedder(session, tiny_tokenizer()).encode(["Alpha beta"])

    [(outputs, feed)] = session.runs
    assert outputs == ["last_hidden_state"]
    assert feed["input_ids"].tolist() == [ids("[CLS]", "alpha", "beta", "[SEP]")]  # lowercased, wrapped
    assert feed["input_ids"].dtype == feed["attention_mask"].dtype == feed["token_type_ids"].dtype == np.int64
    assert vector.dtype == np.float32
    assert np.isclose(np.linalg.norm(vector), 1.0)
    assert np.allclose(vector, expected_vector("[CLS]", "alpha", "beta", "[SEP]"), atol=1e-6)


def test_every_vector_is_normalised():
    vectors = Embedder(FakeSession(), tiny_tokenizer()).encode(["alpha", "beta beta", "gamma word alpha"])

    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)
    # Unnormalised, these rows would be their raw token averages, far from unit length.
    assert not np.isclose(np.linalg.norm(TABLE[ids("[CLS]", "alpha", "[SEP]")].mean(axis=0)), 1.0)


def test_each_text_runs_alone_and_they_come_back_in_order():
    """Padded runs were half as fast and took four times the memory (3.7 GB vs 0.9 GB, measured 2026-11-04)."""
    texts = [["alpha", "beta gamma word", "gamma"][i % 3] for i in range(33)]
    session = FakeSession()

    vectors = Embedder(session, tiny_tokenizer()).encode(texts)

    assert [len(feed["input_ids"]) for _, feed in session.runs] == [1] * 33
    assert vectors.shape == (33, 4)
    for text, vector in zip(texts, vectors):
        assert np.allclose(vector, expected_vector("[CLS]", *text.split(), "[SEP]"), atol=1e-6)


def test_a_long_text_is_cut_at_the_maximum_length_keeping_its_end_marker():
    session = FakeSession()

    Embedder(session, tiny_tokenizer()).encode(["word " * 10_000])

    [(_, feed)] = session.runs
    assert feed["input_ids"].shape == (1, onnx_embedding.MAX_TOKENS) == (1, 1024)
    assert feed["input_ids"][0, 0] == ids("[CLS]")[0] and feed["input_ids"][0, -1] == ids("[SEP]")[0]


def test_only_the_inputs_the_export_declares_are_fed():
    session = FakeSession(inputs=("input_ids", "attention_mask"))

    Embedder(session, tiny_tokenizer()).encode(["alpha"])

    [(_, feed)] = session.runs
    assert sorted(feed) == ["attention_mask", "input_ids"]
