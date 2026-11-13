"""Charts in chat (M14). The model names one dataset of the chat's scope and its columns; PaperLab maps the names to
ids and checks the result with the chart spec a saved chart uses, so a chart in chat never carries a number the model
wrote. The answer is saved as a chat answer with `chart_spec` set, so history, threads and provenance need nothing new.
"""

import uuid
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import chat, datasets, prompts, workspaces
from app.core.chart_spec import MAX_COLORS, ChartSpecAdapter, SeriesChart
from app.core.errors import InvalidInput
from app.core.llm_json import ask_json
from app.core.papers import get_paper
from app.models import LLMOutput

PROMPT_VERSION = 1
SYSTEM_PROMPT, PROMPT_TEMPLATE = prompts.load("chat_chart", PROMPT_VERSION).split(chat.PROMPT_MARKER)
MAX_DATASETS = 20  # ponytail: the first 20 by name; a picker in the composer if workspaces hold more
ChartRefused = InvalidInput  # the API answers 422 with the sentence, which the composer shows as it is


class ChartRequest(BaseModel):
    chart: bool
    reason: str = ""
    type: Literal["bar", "line", "scatter"] = "bar"
    dataset: str = ""
    x: str | None = None
    y: list[str] = Field(default_factory=list, max_length=MAX_COLORS)
    title: str = Field(default="", max_length=200)
    caption: str = Field(default="", max_length=600)


def _label(index: int) -> str:
    return f"D{index + 1}"


def datasets_block(views: list[datasets.DatasetView]) -> str:
    lines = []
    for index, view in enumerate(views):
        columns = ", ".join(c.name + (f" ({c.unit})" if c.unit else "") for c in view.columns)
        first = ", ".join(cell.raw for cell in view.rows[0].cells) if view.rows else "no rows"
        source = f" ({view.paper_title})" if view.paper_title else ""
        lines.append(
            f"{_label(index)} · {view.name}{source} · {view.row_count} rows · columns: {columns} · first row: {first}"
        )
    return "\n".join(lines)


def _column(view: datasets.DatasetView, name: str) -> datasets.ColumnView:
    wanted = name.strip().casefold()
    for column in view.columns:
        if column.name.strip().casefold() == wanted:
            return column
    raise ChartRefused(f"{view.name} has no column “{name}”.")


def build_spec(request: ChartRequest, views: list[datasets.DatasetView]) -> SeriesChart:
    labels = {_label(i): view for i, view in enumerate(views)}
    view = labels.get(request.dataset.strip().upper())
    if view is None:
        raise ChartRefused(f"There is no dataset {request.dataset}.")
    if not request.y:
        raise ChartRefused("The chart names no column to draw.")
    x = _column(view, request.x) if request.x else None
    ys = [_column(view, name) for name in request.y]
    spec = {
        "type": request.type,
        "series": [
            {
                "id": f"s{i + 1}",
                "name": y.name,
                "dataset_id": str(view.id),
                "x": str(x.id) if x else None,
                "y": str(y.id),
            }
            for i, y in enumerate(ys)
        ],
        "axes": {
            "x": {"label": x.name if x else "", "scale": "category" if x and request.type == "bar" else "linear"},
            "y": {"label": ys[0].name if len(ys) == 1 else ""},
        },
    }
    try:
        return ChartSpecAdapter.validate_python(spec)
    except ValidationError as exc:
        raise ChartRefused(f"That chart can't be drawn: {exc.errors()[0]['msg']}.") from exc


async def _scope_datasets(session: AsyncSession, scope: chat.Scope) -> list[datasets.DatasetView]:
    if scope.paper_id is not None:
        await get_paper(session, scope.paper_id)  # 404 for an unknown paper, not "no datasets"
        paper_ids = [scope.paper_id]
    else:
        await workspaces.get(session, scope.workspace_id)
        paper_ids = [p.id for p in await workspaces.papers(session, scope.workspace_id)]
    summaries = [s for paper_id in paper_ids for s in await datasets.list_datasets(session, paper_id)]
    summaries.sort(key=lambda s: (s.paper_title or "", s.name))
    return [await datasets.get_dataset(session, s.id) for s in summaries[:MAX_DATASETS]]


async def ask_chart(session: AsyncSession, scope: chat.Scope, question: str, llm) -> uuid.UUID:
    """Saves and returns a chart answer, or raises ChartRefused with a sentence the reader can act on."""
    views = await _scope_datasets(session, scope)
    if not views:
        raise InvalidInput("no_datasets")
    await session.commit()  # the model can take minutes: hold no transaction meanwhile
    prompt = PROMPT_TEMPLATE.replace("{datasets}", datasets_block(views)).replace("{question}", question)
    request = await ask_json(llm, SYSTEM_PROMPT, prompt, ChartRequest)
    if request is None:
        raise ChartRefused("The model couldn't turn the reply into a chart. Try naming the table and its columns.")
    if not request.chart:
        raise ChartRefused(request.reason or "None of the captured tables holds what was asked for.")
    spec = build_spec(request, views)
    title = request.title.strip() or ", ".join(s.name for s in spec.series)
    output = LLMOutput(
        paper_id=scope.paper_id,
        workspace_id=scope.workspace_id,
        kind="chat",
        question=question,
        content=f"**{title}**\n\n{request.caption.strip()}".strip(),
        chart_spec=spec.model_dump(mode="json"),
        model=llm.model,
        connection_name=llm.connection_name,
        prompt_version=PROMPT_VERSION,
    )
    session.add(output)
    await session.commit()
    return output.id
