"""The built-in search model's files and their download, against a fake Hugging Face (D135, spec §8.3). No network."""

import errno

import pytest
from hub_fakes import ONNX_BYTES, TOKENIZER_BYTES, VARIANT, FakeHub

from app.providers import search_model
from app.providers.search_model import DownloadError, Progress

pytestmark = pytest.mark.anyio

TOTAL = len(ONNX_BYTES) + len(TOKENIZER_BYTES)
ONNX = VARIANT.onnx.path


@pytest.fixture
def hub(monkeypatch):
    monkeypatch.setattr(search_model, "CHUNK", 512)  # several progress events per file
    return FakeHub()


async def fetch(models_dir, hub) -> list[Progress]:
    return [progress async for progress in search_model.download(models_dir, VARIANT, transport=hub.transport)]


def files_in(models_dir) -> list[str]:
    return sorted(str(p.relative_to(models_dir)) for p in models_dir.rglob("*") if p.is_file())


def test_the_pinned_files():
    """Hugging Face's sizes and LFS sha256s at the pinned commit (read 2026-09-18). tokenizer.json is not in LFS: its
    sha256 is of the file itself, whose git blob id matched the tree's."""
    int8, full = search_model.VARIANTS["int8"], search_model.VARIANTS["full"]
    assert search_model.url(int8.onnx) == (
        "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5/resolve/e9b6763023c676ca8431644204f50c2b100d9aab/"
        "onnx/model_int8.onnx"
    )
    assert (int8.name, int8.onnx.size, int8.onnx.sha256) == (
        "nomic-ai/nomic-embed-text-v1.5@int8",
        137_296_292,
        "b4342336debaea79de872370664b0aaeb67dea4605513d00ee236ea871a81f27",
    )
    assert (full.name, full.onnx.path, full.onnx.size, full.onnx.sha256) == (
        "nomic-ai/nomic-embed-text-v1.5",
        "onnx/model.onnx",
        547_310_275,
        "147d5aa88c2101237358e17796cf3a227cead1ec304ec34b465bb08e9d952965",
    )
    assert (
        int8.tokenizer
        == full.tokenizer
        == search_model.ModelFile(
            "tokenizer.json", 711_396, "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"
        )
    )
    assert search_model.SHIPPED in (int8, full)


async def test_a_download_fetches_both_files_and_its_progress_adds_up(tmp_path, hub):
    events = await fetch(tmp_path, hub)

    assert (events[0].file, events[-1].file) == ("tokenizer.json", ONNX)
    assert all(event.total == TOTAL for event in events)
    assert [e.completed for e in events] == sorted(e.completed for e in events)  # never goes back
    assert events[-1].completed == TOTAL
    assert len([e for e in events if e.file == ONNX]) == 1 + len(ONNX_BYTES) // 512  # before the request, per write
    assert files_in(tmp_path) == ["nomic-embed-text-v1.5/onnx/model_int8.onnx", "nomic-embed-text-v1.5/tokenizer.json"]
    assert search_model.path(tmp_path, VARIANT.onnx).read_bytes() == ONNX_BYTES
    assert search_model.present(tmp_path, VARIANT) and search_model.download_bytes(tmp_path, VARIANT) == 0
    assert hub.ranges() == [None, None]  # followed Hugging Face's redirect to the CDN, no Range on a fresh file


async def test_an_interrupted_download_resumes_from_its_part_with_a_range_request(tmp_path, hub):
    hub.cuts[ONNX] = 1024

    with pytest.raises(DownloadError, match="^Can't reach huggingface.co"):
        await fetch(tmp_path, hub)

    part = search_model.path(tmp_path, VARIANT.onnx).with_name("model_int8.onnx.part")
    assert part.read_bytes() == ONNX_BYTES[:1024]
    assert search_model.path(tmp_path, VARIANT.tokenizer).read_bytes() == TOKENIZER_BYTES
    assert not search_model.present(tmp_path, VARIANT)
    assert search_model.download_bytes(tmp_path, VARIANT) == len(ONNX_BYTES) - 1024

    events = await fetch(tmp_path, hub)

    assert events[0] == Progress(ONNX, len(TOKENIZER_BYTES) + 1024, TOTAL)  # the tokenizer isn't fetched again
    assert events[-1].completed == TOTAL
    assert hub.ranges() == [None, None, "bytes=1024-"]
    assert search_model.path(tmp_path, VARIANT.onnx).read_bytes() == ONNX_BYTES
    assert not part.exists()


async def test_a_server_that_ignores_the_range_sends_the_whole_file_and_the_part_starts_again(tmp_path, hub):
    hub.cuts[ONNX] = 1024
    with pytest.raises(DownloadError):
        await fetch(tmp_path, hub)
    hub.ignore_range = True

    events = await fetch(tmp_path, hub)

    assert hub.ranges()[-1] == "bytes=1024-"
    assert search_model.path(tmp_path, VARIANT.onnx).read_bytes() == ONNX_BYTES
    assert [e.completed for e in events] == sorted(e.completed for e in events)  # never goes back


async def test_a_checksum_mismatch_deletes_the_part_and_says_so(tmp_path, hub):
    hub.files[ONNX] = bytes(len(ONNX_BYTES))  # the right size, the wrong bytes

    with pytest.raises(DownloadError, match="^The download was damaged, so it was deleted. Try again.$"):
        await fetch(tmp_path, hub)

    assert files_in(tmp_path) == ["nomic-embed-text-v1.5/tokenizer.json"]  # no part left to resume
    assert search_model.download_bytes(tmp_path, VARIANT) == len(ONNX_BYTES)


async def test_no_network_says_so_and_leaves_nothing_in_place(tmp_path, hub):
    hub.offline = True

    with pytest.raises(
        DownloadError, match="^Can't reach huggingface.co. Check the internet connection and try again: the download"
    ):
        await fetch(tmp_path, hub)

    assert not search_model.present(tmp_path, VARIANT)
    assert search_model.download_bytes(tmp_path, VARIANT) == TOTAL


async def test_an_error_status_says_which(tmp_path, hub):
    hub.status = 503

    with pytest.raises(DownloadError, match="^Hugging Face answered 503. Try again later.$"):
        await fetch(tmp_path, hub)


async def test_a_full_disk_says_so(tmp_path, hub, monkeypatch):
    class FullDisk:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def write(self, chunk):
            raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(search_model, "_open_part", lambda part, resume: FullDisk())

    with pytest.raises(DownloadError, match="^The disk is full. Free some space and try again: the download resumes.$"):
        await fetch(tmp_path, hub)


def test_a_model_is_present_only_with_both_files_at_their_pinned_size(tmp_path):
    onnx, tokenizer = (search_model.path(tmp_path, file) for file in (VARIANT.onnx, VARIANT.tokenizer))
    onnx.parent.mkdir(parents=True)
    onnx.write_bytes(ONNX_BYTES)
    assert not search_model.present(tmp_path, VARIANT)
    tokenizer.write_bytes(TOKENIZER_BYTES[:-1])
    assert not search_model.present(tmp_path, VARIANT)  # the wrong size
    tokenizer.write_bytes(TOKENIZER_BYTES)
    assert search_model.present(tmp_path, VARIANT)
