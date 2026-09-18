"""The built-in search model's arithmetic (D134): text in, one unit-length vector out, the way sentence-transformers
ran nomic-embed-text-v1.5 — tokenize (truncated at MAX_TOKENS), run the model, average the token embeddings over the
attention mask (its 1_Pooling config: mean), L2-normalise (normalize_embeddings=True).

No model files and no onnxruntime import here: embedding.load() builds the session and the tokenizer and hands them to
Embedder, so tests run it with a fake session and a tiny tokenizer.
"""

import numpy as np

BATCH_SIZE = 16  # texts per model run; memory grows with batch x longest text, and chunks are paragraphs
MAX_TOKENS = 8192  # sentence_bert_config.json's max_seq_length, [CLS] and [SEP] included
PAD_ID = 0  # tokenizer.json's [PAD]
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
        # This embedder's own tokenizer: it truncates and pads the way sentence-transformers asked the model to.
        self._tokenizer = tokenizer
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.enable_padding(pad_id=PAD_ID, pad_token="[PAD]")

    def encode(self, texts: list[str]) -> np.ndarray:
        """One unit-length float32 row per text, in order. `texts` is never empty (embedding._encode checks)."""
        return np.concatenate([self._batch(texts[i : i + BATCH_SIZE]) for i in range(0, len(texts), BATCH_SIZE)])

    def _batch(self, texts: list[str]) -> np.ndarray:
        encodings = self._tokenizer.encode_batch(texts)
        feed = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
            "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
        }
        (tokens,) = self._session.run([OUTPUT], {name: feed[name] for name in self._inputs})
        return normalize(mean_pool(tokens, feed["attention_mask"]))
