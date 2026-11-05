"""The built-in search model's arithmetic (D134): text in, one unit-length vector out, the way sentence-transformers
ran nomic-embed-text-v1.5 — tokenize (truncated at MAX_TOKENS), run the model, average the token embeddings over the
attention mask (its 1_Pooling config: mean), L2-normalise (normalize_embeddings=True).

No model files and no onnxruntime import here: embedding.load() builds the session and the tokenizer and hands them to
Embedder, so tests run it with a fake session and a tiny tokenizer.
"""

import numpy as np

# One text per model run. Batches pad every text to the longest, and on real chunks that made embedding half as fast and
# took four times the memory (9.5 vs 21 chunks/s, 3.7 vs 0.9 GB, measured 2026-11-04), with the same vectors.
# The model allows 8,192, but a long chunk costs far more memory: 5.5 GB on the longest texts, against 1.3 GB at 1,024.
# 1.3% of chunks on 10,226 real pages run longer, and no answer changed on 58 sealed questions (measured 2026-11-05).
# Their words stay searchable and are sent whole; only the vector stops at the limit.
MAX_TOKENS = 1024  # [CLS] and [SEP] included
OUTPUT = "last_hidden_state"  # the export's token embeddings, (batch, tokens, 768)


def mean_pool(tokens: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Each text's token embeddings averaged, padding left out: sentence-transformers' mean pooling."""
    weights = mask[:, :, None].astype(tokens.dtype)
    return (tokens * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)


def normalize(vectors: np.ndarray) -> np.ndarray:
    """Each row at unit length, as normalize_embeddings=True did (torch's F.normalize, eps 1e-12)."""
    return vectors / np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None)


class Embedder:
    """An ONNX Runtime session and its tokenizer. `session` needs get_inputs() and run(), as InferenceSession has."""

    def __init__(self, session, tokenizer):
        self._session = session
        # The export decides which of input_ids / attention_mask / token_type_ids it takes; feed exactly those.
        self._inputs = [node.name for node in session.get_inputs()]
        # This embedder's own tokenizer: it truncates the way sentence-transformers asked the model to.
        self._tokenizer = tokenizer
        tokenizer.enable_truncation(max_length=MAX_TOKENS)

    def encode(self, texts: list[str]) -> np.ndarray:
        """One unit-length float32 row per text, in order. `texts` is never empty (embedding._encode checks)."""
        return np.concatenate([self._encode_one(text) for text in texts])

    def _encode_one(self, text: str) -> np.ndarray:
        encoding = self._tokenizer.encode(text)
        feed = {
            "input_ids": np.array([encoding.ids], dtype=np.int64),
            "attention_mask": np.array([encoding.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([encoding.type_ids], dtype=np.int64),
        }
        (tokens,) = self._session.run([OUTPUT], {name: feed[name] for name in self._inputs})
        return normalize(mean_pool(tokens, feed["attention_mask"]))
