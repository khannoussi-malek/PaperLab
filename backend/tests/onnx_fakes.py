"""A fake ONNX session and a tiny real tokenizer, for the built-in search model's tests (no model files, no network)."""

from types import SimpleNamespace

import numpy as np
from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors

WORDS = ["search", "_", "document", "query", ":", "alpha", "beta", "gamma", "word"]
VOCAB = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, **{word: i for i, word in enumerate(WORDS, start=4)}}
ALL_INPUTS = ("input_ids", "attention_mask", "token_type_ids")

# One 4-d row per token id. [PAD] sits far from everything, so pooling that counts padding is visibly wrong.
TABLE = np.array(
    [[1000.0, -1000.0, 1000.0, 0.0], *([i, 1.0, (-1.0) ** i, 0.5] for i in range(1, len(VOCAB)))], dtype=np.float32
)


def tiny_tokenizer() -> Tokenizer:
    """tokenizer.json's pipeline (BERT normaliser and pre-tokenizer, WordPiece, [CLS] … [SEP]) over thirteen tokens,
    so one word is one token and every id can be read in an assertion."""
    tokenizer = Tokenizer(models.WordPiece(VOCAB, unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.BertNormalizer(lowercase=True)
    tokenizer.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    tokenizer.post_processor = processors.TemplateProcessing(
        single="[CLS] $A [SEP]", special_tokens=[("[CLS]", VOCAB["[CLS]"]), ("[SEP]", VOCAB["[SEP]"])]
    )
    return tokenizer


def ids(*tokens: str) -> list[int]:
    return [VOCAB[token] for token in tokens]


def expected_vector(*tokens: str) -> np.ndarray:
    """What the model should give for these tokens: their rows averaged, then scaled to unit length."""
    mean = TABLE[ids(*tokens)].mean(axis=0)
    return mean / np.linalg.norm(mean)


class FakeSession:
    """Stands in for onnxruntime.InferenceSession: token embeddings are TABLE's row per token id. Records every run."""

    def __init__(self, inputs=ALL_INPUTS):
        self.inputs = inputs
        self.runs: list[tuple[list[str], dict[str, np.ndarray]]] = []

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.inputs]

    def run(self, output_names, feed):
        assert set(feed) == set(self.inputs), f"fed {sorted(feed)}, the model takes {sorted(self.inputs)}"
        self.runs.append((output_names, feed))
        return [TABLE[feed["input_ids"]]]
