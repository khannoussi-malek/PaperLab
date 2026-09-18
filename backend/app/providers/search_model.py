"""The built-in search model's files: which ones, pinned where, and their resumable, checksummed download (D135).

nomic-embed-text-v1.5's ONNX exports on Hugging Face, fetched over HTTPS at a pinned commit without huggingface_hub.
Each file is written as `<name>.part`, resumed with a Range request from the part's size, and renamed into place only
once its sha256 matches, so a half-written file is never loaded. A model is *present* when both of its files are in
place at their pinned size (D136). Nothing here reads settings: callers pass the models folder.
"""

import asyncio
import errno
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx

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
SHIPPED = VARIANTS["int8"]

CHUNK = 1 << 20  # bytes per write, and per progress event
TIMEOUT = httpx.Timeout(60, connect=10)

NO_NETWORK = "Can't reach huggingface.co. Check the internet connection and try again: the download resumes."
DAMAGED = "The download was damaged, so it was deleted. Try again."
DISK_FULL = "The disk is full. Free some space and try again: the download resumes."


class DownloadError(Exception):
    """The download stopped; the message is a sentence for the owner."""


@dataclass(frozen=True)
class Progress:
    file: str  # the repo path being fetched
    completed: int  # bytes of the whole download so far, including what earlier tries left in .part files
    total: int  # bytes of the whole download: every file of the variant


def url(file: ModelFile) -> str:
    return f"https://huggingface.co/{REPO}/resolve/{COMMIT}/{file.path}"


def path(models_dir: Path, file: ModelFile) -> Path:
    return models_dir / FOLDER / file.path


def _part(target: Path) -> Path:
    return target.with_name(target.name + ".part")


def _in_place(models_dir: Path, file: ModelFile) -> bool:
    target = path(models_dir, file)
    return target.is_file() and target.stat().st_size == file.size


def present(models_dir: Path, variant: Variant) -> bool:
    return all(_in_place(models_dir, file) for file in variant.files)


def _held(models_dir: Path, file: ModelFile) -> int:
    """Bytes of `file` already here: all of them once it is in place, else what its .part holds."""
    if _in_place(models_dir, file):
        return file.size
    part = _part(path(models_dir, file))
    return min(part.stat().st_size, file.size) if part.is_file() else 0


def download_bytes(models_dir: Path, variant: Variant) -> int:
    """What a download would fetch now (GET /api/embedding): the variant's files minus what is already here."""
    return sum(file.size - _held(models_dir, file) for file in variant.files)


def _sha256(file: Path) -> str:
    with file.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _open_part(part: Path, resume: bool):
    return part.open("ab" if resume else "wb")


async def _fetch(client: httpx.AsyncClient, file: ModelFile, target: Path) -> AsyncIterator[int]:
    """Writes `file` to its .part, resuming from what the part holds, and renames it to `target` once its sha256
    matches. Yields how many bytes the part holds: once the response has settled where it really starts from (a
    server can ignore Range and restart the part), and then after each write, so progress never goes backward."""
    part = _part(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.is_file() else 0
    if have < file.size:
        headers = {"Range": f"bytes={have}-"} if have else {}
        async with client.stream("GET", url(file), headers=headers) as response:
            if response.status_code not in (200, 206):
                raise DownloadError(f"Hugging Face answered {response.status_code}. Try again later.")
            if response.status_code == 200:
                have = 0  # the whole file came back, not the rest of it: start the part again
            yield have
            with _open_part(part, resume=have > 0) as out:
                async for chunk in response.aiter_bytes(CHUNK):
                    out.write(chunk)
                    have += len(chunk)
                    yield have
    else:
        yield have
    if have < file.size:  # the body ended early without an error: keep the part, the next try resumes it
        raise DownloadError(NO_NETWORK)
    if have > file.size or await asyncio.to_thread(_sha256, part) != file.sha256:
        part.unlink()
        raise DownloadError(DAMAGED)
    part.rename(target)


async def download(models_dir: Path, variant: Variant, transport=None) -> AsyncIterator[Progress]:
    """Fetches every file of `variant` not yet in place, with progress. Raises DownloadError: a damaged file's part is
    deleted; after any other error the parts stay, and the next download resumes them."""
    total = sum(file.size for file in variant.files)
    done = sum(file.size for file in variant.files if _in_place(models_dir, file))  # grows by one file at a time
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, transport=transport) as client:
            for file in variant.files:
                if _in_place(models_dir, file):
                    continue
                async for have in _fetch(client, file, path(models_dir, file)):
                    yield Progress(file.path, done + have, total)
                done += file.size
    except httpx.HTTPError as exc:
        raise DownloadError(NO_NETWORK) from exc
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            raise DownloadError(DISK_FULL) from exc
        raise
