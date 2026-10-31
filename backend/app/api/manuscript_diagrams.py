import uuid

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.core import manuscript_diagrams as diagrams
from app.schemas.manuscript_diagrams import DiagramCodeIn, DiagramIn, DiagramOut

router = APIRouter(tags=["manuscripts"])
BASE = "/api/manuscripts/{manuscript_id}/diagrams"


@router.post(BASE, status_code=202)
async def create_diagram(manuscript_id: uuid.UUID, body: DiagramIn, session: SessionDep) -> DiagramOut:
    return DiagramOut(**await diagrams.create(session, manuscript_id, **body.model_dump()))


@router.get(BASE + "/{diagram_id}")
async def get_diagram(manuscript_id: uuid.UUID, diagram_id: uuid.UUID, session: SessionDep) -> DiagramOut:
    return DiagramOut(**await diagrams.state(session, manuscript_id, diagram_id))


@router.put(BASE + "/{diagram_id}/code", status_code=202)
async def set_diagram_code(
    manuscript_id: uuid.UUID, diagram_id: uuid.UUID, body: DiagramCodeIn, session: SessionDep
) -> DiagramOut:
    return DiagramOut(**await diagrams.set_code(session, manuscript_id, diagram_id, body.code))


@router.get(BASE + "/{diagram_id}/pdf", response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
async def diagram_pdf(manuscript_id: uuid.UUID, diagram_id: uuid.UUID, session: SessionDep) -> Response:
    pdf = await diagrams.pdf(session, manuscript_id, diagram_id)
    return Response(pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.post(BASE + "/{diagram_id}/cancel")
async def cancel_diagram(manuscript_id: uuid.UUID, diagram_id: uuid.UUID, session: SessionDep) -> DiagramOut:
    return DiagramOut(**await diagrams.cancel(session, manuscript_id, diagram_id))


@router.delete(BASE + "/{diagram_id}", status_code=204)
async def delete_diagram(manuscript_id: uuid.UUID, diagram_id: uuid.UUID, session: SessionDep) -> None:
    await diagrams.remove(session, manuscript_id, diagram_id)
