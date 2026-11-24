"""The built-in search model's catalog: nomic-embed-text-v1.5's ONNX files, pinned by commit, size and sha256 (D135).
Pure data, so settings can name the shipped model without importing the downloader."""

from dataclasses import dataclass

REPO = "nomic-ai/nomic-embed-text-v1.5"
COMMIT = "e9b6763023c676ca8431644204f50c2b100d9aab"
FOLDER = "nomic-embed-text-v1.5"  # under MODELS_DIR


@dataclass(frozen=True)
class ModelFile:
    path: str  # in the repo, and under MODELS_DIR/FOLDER
    size: int
    sha256: str


@dataclass(frozen=True)
class Variant:
    name: str  # what chunks.embed_model records (D137)
    onnx: ModelFile
    tokenizer: ModelFile

    @property
    def files(self) -> tuple[ModelFile, ModelFile]:
        return (self.tokenizer, self.onnx)  # the small one first: a broken connection shows at once


TOKENIZER = ModelFile("tokenizer.json", 711_396, "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66")
VARIANTS = {
    "int8": Variant(
        f"{REPO}@int8",
        ModelFile(
            "onnx/model_int8.onnx", 137_296_292, "b4342336debaea79de872370664b0aaeb67dea4605513d00ee236ea871a81f27"
        ),
        TOKENIZER,
    ),
    # The same name as the sentence-transformers vectors: parity >= 0.999 keeps them valid (D137).
    "full": Variant(
        REPO,
        ModelFile("onnx/model.onnx", 547_310_275, "147d5aa88c2101237358e17796cf3a227cead1ec304ec34b465bb08e9d952965"),
        TOKENIZER,
    ),
}
# The variant PaperLab downloads and runs (spec §4). The other is never offered for download.
SHIPPED = VARIANTS["full"]
