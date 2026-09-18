"""Hugging Face behind httpx.MockTransport, and a two-file model small enough to serve from it. No network."""

import hashlib

import httpx

from app.providers.search_model import COMMIT, REPO, ModelFile, Variant

ONNX_BYTES = bytes(range(256)) * 8  # 2,048 bytes
TOKENIZER_BYTES = b'{"model": {"type": "WordPiece"}}'


def model_file(path: str, content: bytes) -> ModelFile:
    return ModelFile(path, len(content), hashlib.sha256(content).hexdigest())


VARIANT = Variant(
    "test-model@int8", model_file("onnx/model_int8.onnx", ONNX_BYTES), model_file("tokenizer.json", TOKENIZER_BYTES)
)


async def _dropped(data: bytes):
    yield data
    raise httpx.ReadError("connection reset by peer")


class FakeHub:
    """Serves VARIANT's files the way Hugging Face does: the pinned resolve URL answers 302 to a CDN host, which honours
    `Range: bytes=N-` with a 206. Records every request. `cuts[path] = n` drops that file's next body after n bytes;
    `offline` refuses every connection; `status` answers every request with that status; `ignore_range` answers a
    Range request with the whole file (200); `files` can be edited to serve other bytes."""

    CDN = "cdn.hf.test"

    def __init__(self):
        self.files = {VARIANT.onnx.path: ONNX_BYTES, VARIANT.tokenizer.path: TOKENIZER_BYTES}
        self.requests: list[httpx.Request] = []
        self.cuts: dict[str, int] = {}
        self.offline = False
        self.status: int | None = None
        self.ignore_range = False
        self.transport = httpx.MockTransport(self._handle)

    def ranges(self) -> list[str | None]:
        """The Range header of each request the CDN answered."""
        return [r.headers.get("Range") for r in self.requests if r.url.host == self.CDN]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.offline:
            raise httpx.ConnectError("no route to host", request=request)
        if self.status is not None:
            return httpx.Response(self.status)
        prefix = f"/{REPO}/resolve/{COMMIT}/"
        if request.url.host == "huggingface.co":
            assert request.url.path.startswith(prefix), f"unpinned request: {request.url}"
            return httpx.Response(
                302, headers={"Location": f"https://{self.CDN}/{request.url.path.removeprefix(prefix)}"}
            )
        name = request.url.path.lstrip("/")
        asked = request.headers.get("Range")
        start = 0 if asked is None or self.ignore_range else int(asked.removeprefix("bytes=").removesuffix("-"))
        status, body = 206 if start else 200, self.files[name][start:]
        if name in self.cuts:
            return httpx.Response(status, content=_dropped(body[: self.cuts.pop(name)]))
        return httpx.Response(status, content=body)
