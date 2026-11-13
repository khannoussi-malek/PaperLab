import uuid
from typing import Annotated

from fastapi import APIRouter, Form, Response, UploadFile

from app.api.deps import LLMByModelIdDep, SessionDep
from app.core import capture, datasets, number_suggest
from app.core.numbers import find_numbers
from app.schemas.datasets import (
    DatasetCreate,
    DatasetOut,
    DatasetRename,
    DatasetSummaryOut,
    GridIn,
    NumberAddedOut,
    NumberCandidateOut,
    NumberCandidatesRequest,
    NumberCreate,
    NumberSuggestionsOut,
    NumberSuggestRequest,
    TablePreviewOut,
    TablePreviewRequest,
)

router = APIRouter(tags=["datasets"])


@router.post("/api/papers/{paper_id}/tables/preview")
async def preview_table(paper_id: uuid.UUID, payload: TablePreviewRequest, session: SessionDep) -> TablePreviewOut:
    return await capture.preview_table(session, paper_id, payload.page, payload.region)


@router.post("/api/papers/{paper_id}/numbers", status_code=201)
async def add_number(paper_id: uuid.UUID, payload: NumberCreate, session: SessionDep) -> NumberAddedOut:
    return await capture.add_number(
        session, paper_id, payload.label, payload.raw, payload.unit, payload.page, payload.bbox,
        suggested=payload.suggested,
    )


@router.post("/api/papers/{paper_id}/numbers/suggestions")
async def suggest_numbers(
    paper_id: uuid.UUID, payload: NumberSuggestRequest, session: SessionDep, llm: LLMByModelIdDep
) -> NumberSuggestionsOut:
    """The section's numbers a model found, each kept only when its quote is in the section and holds the value (D33).
    Nothing is saved; `?model_id=` picks the model. 422 unknown_section."""
    found = await number_suggest.suggest(session, paper_id, payload.section_title, llm)
    return NumberSuggestionsOut.model_validate(found)


@router.post("/api/numbers/candidates")
async def number_candidates(payload: NumberCandidatesRequest) -> list[NumberCandidateOut]:
    return find_numbers(payload.text)


@router.get("/api/datasets")
async def list_datasets(session: SessionDep, paper_id: uuid.UUID | None = None) -> list[DatasetSummaryOut]:
    return await datasets.list_datasets(session, paper_id)


@router.post("/api/datasets", status_code=201)
async def create_dataset(payload: DatasetCreate, session: SessionDep) -> DatasetOut:
    return await datasets.create_dataset(
        session,
        payload.name,
        payload.kind,
        payload.grid.to_core(),
        paper_id=payload.paper_id,
        page=payload.page,
        region=payload.region,
    )


@router.post("/api/datasets/import", status_code=201)
async def import_dataset(
    file: UploadFile, session: SessionDep, name: Annotated[str | None, Form()] = None
) -> DatasetOut:
    # One byte over the limit is enough for core to refuse it, without reading a huge upload into memory.
    return await capture.import_csv(session, name, await file.read(capture.MAX_IMPORT_BYTES + 1))


@router.get("/api/datasets/{dataset_id}")
async def get_dataset(dataset_id: uuid.UUID, session: SessionDep) -> DatasetOut:
    return await datasets.get_dataset(session, dataset_id)


@router.patch("/api/datasets/{dataset_id}")
async def rename_dataset(dataset_id: uuid.UUID, payload: DatasetRename, session: SessionDep) -> DatasetOut:
    return await datasets.rename_dataset(session, dataset_id, payload.name)


@router.put("/api/datasets/{dataset_id}/grid")
async def save_grid(dataset_id: uuid.UUID, payload: GridIn, session: SessionDep, force: bool = False) -> DatasetOut:
    return await datasets.save_grid(session, dataset_id, payload.to_core(), force=force)


@router.delete("/api/datasets/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: uuid.UUID, session: SessionDep, force: bool = False) -> Response:
    await datasets.delete_dataset(session, dataset_id, force=force)
    return Response(status_code=204)
