import uuid

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.core import charts, notes
from app.schemas.charts import ChartCreate, ChartOut, ChartSummaryOut, ChartUpdate, ResolvedDataOut, ResolveRequest
from app.schemas.notes import NoteOut

router = APIRouter(tags=["charts"])


@router.get("/api/charts")
async def list_charts(session: SessionDep) -> list[ChartSummaryOut]:
    return await charts.list_charts(session)


@router.post("/api/charts", status_code=201)
async def create_chart(payload: ChartCreate, session: SessionDep) -> ChartOut:
    return await charts.create_chart(session, payload.title, payload.spec)


@router.post("/api/charts/resolve")
async def resolve_chart(payload: ResolveRequest, session: SessionDep) -> ResolvedDataOut:
    """The current cells a spec names, for drawing a saved chart or previewing an unsaved one."""
    return await charts.resolve(session, payload.spec)


@router.get("/api/charts/{chart_id}")
async def get_chart(chart_id: uuid.UUID, session: SessionDep) -> ChartOut:
    return await charts.get_chart(session, chart_id)


@router.patch("/api/charts/{chart_id}")
async def update_chart(chart_id: uuid.UUID, payload: ChartUpdate, session: SessionDep) -> ChartOut:
    return await charts.update_chart(session, chart_id, title=payload.title, spec=payload.spec)


@router.post("/api/charts/{chart_id}/duplicate", status_code=201)
async def duplicate_chart(chart_id: uuid.UUID, session: SessionDep) -> ChartOut:
    return await charts.duplicate_chart(session, chart_id)


@router.delete("/api/charts/{chart_id}", status_code=204)
async def delete_chart(chart_id: uuid.UUID, session: SessionDep) -> Response:
    await charts.delete_chart(session, chart_id)
    return Response(status_code=204)


@router.post("/api/charts/{chart_id}/note", status_code=201)
async def add_to_note(chart_id: uuid.UUID, session: SessionDep) -> NoteOut:
    """A new note showing the chart, anchored where its data sits in each paper."""
    return await notes.create_chart_note(session, chart_id, await charts.chart_anchors(session, chart_id))


@router.put("/api/notes/{note_id}/charts/{chart_id}", status_code=204)
async def attach_chart(note_id: uuid.UUID, chart_id: uuid.UUID, session: SessionDep) -> Response:
    await notes.attach_chart(session, note_id, chart_id)
    return Response(status_code=204)


@router.delete("/api/notes/{note_id}/charts/{chart_id}", status_code=204)
async def detach_chart(note_id: uuid.UUID, chart_id: uuid.UUID, session: SessionDep) -> Response:
    await notes.detach_chart(session, note_id, chart_id)
    return Response(status_code=204)
