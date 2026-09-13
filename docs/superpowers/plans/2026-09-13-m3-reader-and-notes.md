# M3 Reader and Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read an uploaded paper in the browser, select a passage, save it as a note anchored to the exact spot, and see it highlighted again after a reload. No LLM anywhere.

**Architecture:**
- **Backend:** notes CRUD in `backend/app/core/notes.py`, which holds the provenance rules. Thin FastAPI routers expose it, plus routes to serve and delete a paper's PDF.
- **Frontend:** a Vite/React app renders each page with PDF.js (canvas + `TextLayerBuilder`). It converts browser selections into PDF-point rectangles (the same coordinate system PyMuPDF stores for chunks) and draws highlights from those rectangles at any zoom.
  - From Task 4.5 on, the UI is built from shadcn/ui components on Tailwind CSS 4, with a light/dark toggle and tokens from `frontend/design-system/MASTER.md` (derived from ui-ux-pro-max).
  - Server data goes through TanStack Query hooks in `frontend/src/api/queries.ts`, wrapping the typed `api` client.
- **Testing:** every task ends with automated tests that exercise what it built.
  - Backend: pytest against real Postgres.
  - Pure frontend logic: Vitest.
  - Every user-visible flow: Playwright against the real stack. Library, reader rendering and zoom, note create/edit/delete, and cross-page selection each have a spec.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, pytest + anyio + httpx, React 19, Vite 8, TypeScript 6, pdfjs-dist 6.3.289, Vitest 5.0.0, Playwright 1.63.0, openapi-typescript 7.13.0, Tailwind CSS 4.3.3, shadcn/ui (CLI 4.21.0, style `radix-nova`), lucide-react, TanStack Query 5.102.8.

**Spec:** [docs/superpowers/specs/2026-09-13-paperlab-brief.md](../specs/2026-09-13-paperlab-brief.md). Build order step 3. Read it together with the [roadmap](2026-09-13-paperlab-roadmap.md), whose decision log (D1–D24) explains the non-obvious choices below. D24 (UI stack) supersedes D14 (no data-fetching library).

## Global Constraints

- "Frontend: PDF.js viewer, text selection, highlight → note. **No LLM anywhere yet.**"
- "If this doesn't feel good to use, stop and fix it before building on top."
- `grep -r "fastapi" backend/app/core/` returns nothing.
- Provenance rules are implemented in `backend/app/core/notes.py`, nowhere else. "The UI shows provenance on every note — a badge and a distinct background."
- "Store PDF points and page dimensions; convert at render time." Anchors are stored as a list of `[x0, y0, x1, y1]` rects in PDF points, top-left origin, pages 1-based (D1, D2).
- "Generate frontend types from FastAPI's OpenAPI schema (`openapi-typescript`) as a build step, from day one."
- `async_sessionmaker(expire_on_commit=False)`; no implicit lazy loads; no blocking calls inside async routes.
- Pinned versions: `create-vite@9.2.1`, `pdfjs-dist@6.3.289`, `vitest@5.0.0`, `@playwright/test@1.63.0`, `openapi-typescript@7.13.0` (via `npx`, D12), `tailwindcss@4.3.3`, `@tailwindcss/vite@4.3.3`, `shadcn@4.21.0` (via `npx`), `@tanstack/react-query@5.102.8`.
- **UI rules (from Task 4.5 on, D24):**
  - Build UI from shadcn/ui components and Tailwind utility classes. Add components with `npx shadcn@4.21.0 add <name>` or the shadcn MCP server; never hand-copy one.
  - No per-feature `.css` files. The only stylesheets are `src/index.css` (tokens) and PDF.js's `pdf_viewer.css`.
  - Every UI task reads `frontend/design-system/MASTER.md` first and ends with its "Pre-delivery check" in both themes.
  - Server state goes through `src/api/queries.ts` hooks; components never call `api.*` for reads directly.
  - Keep the class names and accessible names the Playwright specs use; add styling next to them.
- Ports: API `:8000`, Postgres `:5433`, frontend `:5180` (D16).
- Commits: `<type>: <description>`, no attribution trailer.

## Testing rules for this plan

These follow the roadmap's testing policy; every task must meet them.

1. **A task is not done until its automated tests pass.** Manual checks (Task 5 Step 9, Task 7 Step 1) are extra and never replace a test.
2. **Red first.** Write the test before the code and watch it fail. Where the UI already exists and a new E2E spec can't be red first (Tasks 3, 4.5 and 5), a step introduces a named deliberate bug, shows the spec failing, then undoes the bug.
3. **Coverage by layer:**
   - Each core function: a service test, including its error branches.
   - Each API route: an HTTP test for success and for every error status it returns.
   - Each pure frontend function: a Vitest test.
   - Each user-visible flow: a Playwright spec.
4. **E2E specs use the real stack, and the `paperId` fixture** (`frontend/e2e/fixtures.ts`), which uploads its own paper and deletes it afterwards even when the test fails. Specs are type-checked (`npm run typecheck:e2e`) and run one at a time (`workers: 1`) because they share one library.
5. **A red test that isn't yours means stop.** If a test outside the current task goes red, use superpowers:systematic-debugging before touching it.

## Verified before writing

The final code in this plan was executed while writing it; every full-file block was diffed against the files that ran:
- **Backend:** 12 pytest tests passed against the compose Postgres; Ruff clean. With the M1–M2 test pack from `main` plus `tests/test_notes_edges.py`, 47 tests pass at 97.5% coverage (100% on `core/notes.py`, `api/notes.py`, `schemas/notes.py`).
- **Frontend:** `tsc -b` clean (including the intermediate versions in Tasks 3 and 5); 6 Vitest tests passed; `vite build` succeeds; `npm run typecheck:e2e` clean.
- **E2E:** all 9 Playwright tests pass against a full isolated stack.
  - Each spec was also run against the app as it is at its own task: the Task 3 app passes 2, the Task 5 reader passes 4, and the finished app passes 9.
  - The Task 6 red step (its spec against the Task 5 reader) fails 5 of 5 as described, and cleanup still runs.
  - Vite in Docker picks up edits from the bind mount.
- **Mutation check:** 7 deliberate bugs, each caught by the spec named in its step. The bugs are:
  - Highlight ignores zoom.
  - No text layer.
  - Blank canvas.
  - Cross-page selection allowed.
  - Human badge mislabelled.
  - Edit never saved.
  - Library stops polling.
- **Red-step messages in Tasks 1–4:** predicted, not captured.

Three findings are baked in:
- `getDocument` takes an object, not a URL string.
- `pdf_viewer.mjs` crashes unless `pdfjs-dist` is evaluated first (hence `pdfjs.ts`).
- `TextLayerBuilder.render`'s types wrongly require `images`.

**Tasks 4.5–6 (UI stack rewrite, D24)** were replayed on a clean export of branch `m3-reader-notes` at `d1daecc` (Task 4 done), then re-run with `6594a1d`'s `coords.ts` (transitive line merge). The replay ran every command in Task 4.5 as written and used the exact file blocks in this plan. Results:
- **After Task 4.5:** `tsc -b` clean; `Tests  9 passed (9)` (route 2, coords 5, queries 2); `vite build` succeeds; `4 passed` (3 library + 1 theme). The theme spec fails against the Task 4 app first.
- **After Task 5:** `6 passed`.
- **Task 6's spec, before its code:** fails 5 of 5 as described.
- **After Task 6:** `11 passed`; `npm run typecheck:e2e` clean.
- **Deliberate-bug checks:** all 7 were re-run on the new UI (library stops polling, no text layer, blank canvas, highlight ignores zoom, cross-page allowed, human badge mislabelled, edit never saved), and each fails its named spec.
- **Also checked:**
  - Every token pair in `MASTER.md` meets WCAG AA.
  - The shadcn MCP server answers `tools/list` when started as `.mcp.json` runs it.
  - Light and dark screenshots were reviewed.

Five more findings are baked in:
- `shadcn init` fails `Validating Tailwind CSS` unless `src/index.css` already imports Tailwind, so Task 4.5 writes that line first.
- TypeScript 6 deprecates `baseUrl`, so the `@/*` alias uses `paths` alone.
- Tailwind's reset doesn't disturb PDF.js: it only sets `display: block` on `canvas`, and `pdf_viewer.css` is unlayered, so it wins over `@layer base`. `reader-render.spec.ts` confirms the text layer stays on PyMuPDF's rects at three zooms.
- TanStack Query retries failed queries 3 times by default, which delays a 404 alert past the spec timeout. Hence `retry: false`.
- The compose frontend keeps `node_modules` in an anonymous volume, so new dependencies need `docker compose up -d --build -V frontend`.

## File Structure

```
backend/
  pyproject.toml                     modify: ruff + httpx dev deps, ruff config
  app/models/note.py                 create: Note (mapped), note_anchors (Core Table), Provenance
  app/models/__init__.py             modify: export them
  app/core/notes.py                  create: provenance rules + note/anchor services (no fastapi)
  app/core/papers.py                 modify: delete_paper, get_paper_file
  app/schemas/papers.py              modify: Rect tuple alias, ChunkOut.bbox uses it
  app/schemas/notes.py               create: AnchorIn/Out, NoteCreate/Update/Out
  app/api/deps.py                    create: SessionDep
  app/api/notes.py                   create: notes routes
  app/api/papers.py                  rewrite: SessionDep, + DELETE paper, + GET file
  app/api/health.py                  modify: SessionDep
  app/main.py                        modify: include notes router
  tests/conftest.py                  create: rolled-back DB session + httpx client fixtures
  tests/test_notes.py                create: service tests
  tests/test_notes_api.py            create: HTTP tests
  tests/test_notes_edges.py          create: error branches and unknown ids (Task 2 Step 10a)
docker-compose.yml                   modify: frontend service
README.md                            modify: frontend + test commands
.mcp.json                            create (Task 4.5): shadcn MCP server for agents
frontend/                            create via create-vite, then:
  package.json                       modify: scripts, deps (Task 4.5 adds Tailwind, shadcn deps, TanStack Query, fonts)
  vite.config.ts                     rewrite: /api proxy, vitest include (Task 4.5: + Tailwind plugin, @ alias)
  tsconfig.json, tsconfig.app.json   modify (Task 4.5): @/* paths
  components.json                    generated (Task 4.5): shadcn config
  design-system/MASTER.md            create (Task 4.5): tokens, rules, pre-delivery check
  Dockerfile, .dockerignore          create
  playwright.config.ts               create: real stack, workers 1, 10 s action timeout
  tsconfig.e2e.json                  create: type-checks e2e/ (npm run typecheck:e2e)
  .gitignore                         modify: playwright output
  src/index.css                      rewrite: base tokens + buttons (Task 4.5: Tailwind + theme tokens)
  src/main.tsx                       rewrite (Task 4.5): QueryClientProvider + ThemeProvider
  src/App.tsx                        rewrite: route → page
  src/api/schema.d.ts                generated (committed)
  src/api/client.ts                  create: typed fetch wrappers
  src/api/queries.ts (+ .test.ts)    create (Task 4.5): TanStack Query hooks, poll interval
  src/components/ui/*, src/lib/utils.ts                  generated (Task 4.5): shadcn components
  src/components/theme-provider.tsx, mode-toggle.tsx     create (Task 4.5): light/dark/system
  src/lib/route.ts (+ .test.ts)      create: hash routing
  src/features/library/LibraryPage.tsx                   create (Task 3), rewrite on components (Task 4.5)
  src/features/library/library.css                       create (Task 3), delete (Task 4.5)
  src/features/reader/coords.ts (+ .test.ts)             create: the three coordinate systems
  src/features/reader/pdfjs.ts                           create: the only PDF.js import point
  src/features/reader/usePdfDocument.ts                  create
  src/features/reader/PdfPage.tsx                        create: canvas + text layer + overlay
  src/features/reader/zoom.ts, ReaderToolbar.tsx         create (Task 5): zoom steps, toolbar
  src/features/reader/selection.ts                       create: browser selection → anchor
  src/features/reader/ReaderPage.tsx                     create
  src/features/notes/NotesPanel.tsx, NoteCard.tsx, NoteComposer.tsx, ProvenanceBadge.tsx   create
  e2e/fixtures/make_sample_paper.py, sample-paper.pdf    create (Task 3)
  e2e/fixtures.ts                                        create (Task 3): paperId fixture + selection helpers
  e2e/library.spec.ts                                    create (Task 3): upload → ready → delete; non-PDF error; retry
  e2e/theme.spec.ts                                      create (Task 4.5): toggle, reload, system preference
  e2e/reader-render.spec.ts                              create (Task 5): ink, text layer on chunk at 3 zooms, missing paper
  e2e/highlight-to-note.spec.ts                          create (Task 6): create, zoom, edit, delete, cross-page
```

---

### Task 0: Baseline commit and M3 worktree

M1–M2 exist only as uncommitted files. Commit them, with lint config, before branching.

**Files:**
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: a `main` branch containing M1–M2 and the docs, plus a worktree on branch `m3-reader-notes` with the stack running from it.

- [ ] **Step 1: Add Ruff**

```bash
cd backend && uv add --dev ruff
```

Append to `backend/pyproject.toml`:

```toml
[tool.ruff]
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I"]
```

- [ ] **Step 2: Lint and test the baseline**

Run: `cd backend && uv run ruff check . && uv run pytest -q`
Expected: `All checks passed!`, then `3 passed`.

- [ ] **Step 3: Commit the baseline to main**

Do not add `.claude/`; that is the owner's call (roadmap K6).

```bash
git switch -c m1-m2-foundation
git add .gitignore .env.example README.md docker-compose.yml backend docs
git status --short   # expect nothing staged from .claude/, no .env, no .venv
git commit -m "feat: compose stack, schema migration, and PDF ingest pipeline (M1-M2)"
git switch main
git merge --ff-only m1-m2-foundation
git branch -d m1-m2-foundation
```

- [ ] **Step 4: Create the M3 worktree**

Use superpowers:using-git-worktrees to create a worktree on a new branch `m3-reader-notes`. All paths in the rest of this plan are relative to that worktree root.

- [ ] **Step 5: Run the stack from the worktree**

`.env` is gitignored and therefore missing in a fresh worktree.

```bash
cp .env.example .env
docker compose up -d --build
curl -s localhost:8000/api/health
```

Expected: `{"orm_roundtrip":true,"raw_sql_nearest_is_self":true}`

---

### Task 1: Notes domain (provenance rules, anchors, paper deletion)

**Files:**
- Create: `backend/app/models/note.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/core/notes.py`
- Modify: `backend/app/core/papers.py` (append `delete_paper`)
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_notes.py`

**Interfaces:**
- Consumes (existing):
  - `app.core.papers.get_paper(session, paper_id: UUID) -> Paper`, which raises `NotFound`.
  - `app.core.chunking.join_lines(lines: list[str]) -> str`.
  - `app.core.errors.InvalidInput`, `NotFound`.
  - `app.models.Paper`.
- Produces:
  - `app.models.Note`, `app.models.Provenance` (`HUMAN="human"`, `LLM="llm"`, `LLM_EDITED="llm_edited"`), `app.models.note_anchors` (Core `Table`).
  - `app.core.notes.Anchor(paper_id: UUID, page: int, bbox: list[tuple[float, float, float, float]], quoted_text: str)`, a frozen dataclass.
  - `app.core.notes.NoteView(id, body, provenance, source_id, created_at, updated_at, anchors: list[Anchor])`, a frozen dataclass.
  - `app.core.notes`:
    - `create_human_note(session, body: str, anchor: Anchor) -> NoteView`
    - `list_notes_for_paper(session, paper_id) -> list[NoteView]` (reading order)
    - `update_note_body(session, note_id, body: str) -> NoteView`
    - `delete_note(session, note_id) -> None`
    - `edited_provenance(current: str) -> str`
    - `normalize_quote(text: str) -> str`
  - `app.core.papers.delete_paper(session, paper_id) -> None`.
  - pytest fixtures `session` (an `AsyncSession` rolled back after each test) and `client` (an `httpx.AsyncClient` bound to that session).

- [ ] **Step 1: Add httpx for API tests**

Run: `cd backend && uv add --dev "httpx>=0.28"`

- [ ] **Step 2: Write the test fixtures**

Create `backend/tests/conftest.py`:

```python
import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_session
from app.main import create_app

# The compose Postgres, published on the host. Every test runs inside a transaction that is
# rolled back afterwards, so tests can share the dev database without leaving rows behind.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://paperlab:paperlab@localhost:5433/paperlab"
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # create_savepoint: a service's session.commit() only releases a savepoint.
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as test_session:
            yield test_session
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def client(session):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
```

- [ ] **Step 3: Write the failing service tests**

Create `backend/tests/test_notes.py`:

```python
import uuid

import pytest
from sqlalchemy import func, select

from app.core import notes, papers
from app.core.errors import InvalidInput, NotFound
from app.models import Note, Paper, Provenance

pytestmark = pytest.mark.anyio


async def make_paper(session, page_count=3, file_path="/nonexistent.pdf") -> Paper:
    paper = Paper(title="test paper", file_path=file_path, page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


def anchor(paper: Paper, page=1, top=400.0, quote="effective trans-\nfer learning") -> notes.Anchor:
    return notes.Anchor(paper_id=paper.id, page=page, bbox=[(72.0, top, 290.0, top + 10)], quoted_text=quote)


async def test_create_human_note_normalizes_body_and_quote(session):
    paper = await make_paper(session)

    note = await notes.create_human_note(session, "  worth citing ", anchor(paper))

    assert note.provenance == Provenance.HUMAN
    assert note.body == "worth citing"
    assert note.anchors == [notes.Anchor(paper.id, 1, [(72.0, 400.0, 290.0, 410.0)], "effective transfer learning")]


async def test_create_rejects_page_outside_paper(session):
    paper = await make_paper(session, page_count=3)
    with pytest.raises(InvalidInput):
        await notes.create_human_note(session, "", anchor(paper, page=4))


async def test_create_rejects_unknown_paper(session):
    never_saved = Paper(id=uuid.uuid4(), title="ghost", file_path="/ghost.pdf")
    with pytest.raises(NotFound):
        await notes.create_human_note(session, "", anchor(never_saved))


async def test_list_notes_in_reading_order(session):
    paper = await make_paper(session)
    page_two = await notes.create_human_note(session, "p2", anchor(paper, page=2, top=100))
    page_one_low = await notes.create_human_note(session, "p1 low", anchor(paper, page=1, top=500))
    page_one_high = await notes.create_human_note(session, "p1 high", anchor(paper, page=1, top=100))

    listed = await notes.list_notes_for_paper(session, paper.id)

    assert [n.id for n in listed] == [page_one_high.id, page_one_low.id, page_two.id]


async def test_editing_llm_note_flips_provenance_but_human_stays_human(session):
    paper = await make_paper(session)
    human = await notes.create_human_note(session, "mine", anchor(paper))
    llm_note = Note(body="model said", provenance=Provenance.LLM)
    session.add(llm_note)
    await session.commit()

    assert (await notes.update_note_body(session, human.id, "still mine")).provenance == Provenance.HUMAN
    assert (await notes.update_note_body(session, llm_note.id, "model said")).provenance == Provenance.LLM
    assert (await notes.update_note_body(session, llm_note.id, "I rewrote it")).provenance == Provenance.LLM_EDITED


async def test_delete_note(session):
    paper = await make_paper(session)
    note = await notes.create_human_note(session, "", anchor(paper))

    await notes.delete_note(session, note.id)

    assert await notes.list_notes_for_paper(session, paper.id) == []
    with pytest.raises(NotFound):
        await notes.delete_note(session, note.id)


async def test_deleting_paper_removes_file_and_anchors_but_keeps_notes(session, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    paper = await make_paper(session, page_count=1, file_path=str(pdf))
    note = await notes.create_human_note(session, "keep me", anchor(paper))

    await papers.delete_paper(session, paper.id)

    assert not pdf.exists()
    assert await session.scalar(select(func.count()).select_from(Note).where(Note.id == note.id)) == 1
    with pytest.raises(NotFound):
        await notes.list_notes_for_paper(session, paper.id)
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_notes.py -q`
Expected: collection error `ImportError: cannot import name 'notes' from 'app.core'`.

- [ ] **Step 5: Add the models**

Create `backend/app/models/note.py`:

```python
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, ForeignKey, Integer, Table, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Provenance(StrEnum):
    HUMAN = "human"
    LLM = "llm"
    LLM_EDITED = "llm_edited"


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    body: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text)
    # The database enforces the FK to llm_outputs; that table gets a mapping in M4.
    source_id: Mapped[uuid.UUID | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


# A Core Table, not a mapped class: the primary key includes the jsonb bbox, and the ORM
# identity map can't hash a list. Anchors are only inserted and read in bulk anyway.
note_anchors = Table(
    "note_anchors",
    Base.metadata,
    Column("note_id", UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("paper_id", UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True),
    Column("chunk_id", UUID(as_uuid=True)),
    Column("page", Integer, primary_key=True),
    Column("bbox", JSONB, primary_key=True),
    Column("quoted_text", Text),
)
```

Replace `backend/app/models/__init__.py` with:

```python
from app.models.base import Base
from app.models.note import Note, Provenance, note_anchors
from app.models.paper import Chunk, Paper, PaperStatus

__all__ = ["Base", "Chunk", "Note", "Paper", "PaperStatus", "Provenance", "note_anchors"]
```

- [ ] **Step 6: Write the notes service**

Create `backend/app/core/notes.py`:

```python
"""Notes and their anchors. The provenance rules live here and nowhere else:

- LLM responses go to llm_outputs, never directly into notes.            (M4)
- Promoting an LLM fragment creates a note with provenance='llm' + source_id. (M4)
- Editing an 'llm' note flips it to 'llm_edited'.                          (here)
- Notes created through MCP get provenance='llm'.                          (M6)
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chunking import join_lines
from app.core.errors import InvalidInput, NotFound
from app.core.papers import get_paper
from app.models import Note, Provenance, note_anchors

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class Anchor:
    paper_id: uuid.UUID
    page: int
    bbox: list[Rect]
    quoted_text: str


@dataclass(frozen=True)
class NoteView:
    id: uuid.UUID
    body: str
    provenance: str
    source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    anchors: list[Anchor]


def edited_provenance(current: str) -> str:
    return Provenance.LLM_EDITED if current == Provenance.LLM else current


def normalize_quote(text: str) -> str:
    """Browser selections keep the PDF's line breaks ("trans-\\nfer"); store reading text."""
    return join_lines(text.splitlines())


def reading_position(note: NoteView, paper_id: uuid.UUID) -> tuple[int, float, float]:
    return min((a.page, r[1], r[0]) for a in note.anchors if a.paper_id == paper_id for r in a.bbox)


async def _get_note(session: AsyncSession, note_id: uuid.UUID) -> Note:
    note = await session.get(Note, note_id)
    if note is None:
        raise NotFound(f"note {note_id} not found")
    return note


async def _with_anchors(session: AsyncSession, notes: list[Note]) -> list[NoteView]:
    rows = await session.execute(select(note_anchors).where(note_anchors.c.note_id.in_([n.id for n in notes])))
    anchors: dict[uuid.UUID, list[Anchor]] = {}
    for row in rows:
        anchor = Anchor(
            paper_id=row.paper_id,
            page=row.page,
            bbox=[tuple(r) for r in row.bbox],
            quoted_text=row.quoted_text or "",
        )
        anchors.setdefault(row.note_id, []).append(anchor)
    return [
        NoteView(
            id=n.id,
            body=n.body,
            provenance=n.provenance,
            source_id=n.source_id,
            created_at=n.created_at,
            updated_at=n.updated_at,
            anchors=anchors.get(n.id, []),
        )
        for n in notes
    ]


async def create_human_note(session: AsyncSession, body: str, anchor: Anchor) -> NoteView:
    paper = await get_paper(session, anchor.paper_id)
    if paper.page_count is not None and not 1 <= anchor.page <= paper.page_count:
        raise InvalidInput(f"page {anchor.page} is outside 1..{paper.page_count}")
    quote = normalize_quote(anchor.quoted_text)
    if not quote:
        raise InvalidInput("an anchor needs the quoted text")

    note = Note(body=body.strip(), provenance=Provenance.HUMAN)
    session.add(note)
    await session.flush()
    await session.execute(
        insert(note_anchors).values(
            note_id=note.id,
            paper_id=anchor.paper_id,
            page=anchor.page,
            bbox=[list(r) for r in anchor.bbox],
            quoted_text=quote,
        )
    )
    await session.commit()
    await session.refresh(note)
    return (await _with_anchors(session, [note]))[0]


async def list_notes_for_paper(session: AsyncSession, paper_id: uuid.UUID) -> list[NoteView]:
    await get_paper(session, paper_id)
    anchored_here = select(note_anchors.c.note_id).where(note_anchors.c.paper_id == paper_id)
    notes = list(await session.scalars(select(Note).where(Note.id.in_(anchored_here))))
    views = await _with_anchors(session, notes)
    return sorted(views, key=lambda v: reading_position(v, paper_id))


async def update_note_body(session: AsyncSession, note_id: uuid.UUID, body: str) -> NoteView:
    note = await _get_note(session, note_id)
    new_body = body.strip()
    if new_body != note.body:
        await session.execute(
            update(Note)
            .where(Note.id == note_id)
            .values(body=new_body, provenance=edited_provenance(note.provenance), updated_at=func.now())
        )
        await session.commit()
        await session.refresh(note)
    return (await _with_anchors(session, [note]))[0]


async def delete_note(session: AsyncSession, note_id: uuid.UUID) -> None:
    await _get_note(session, note_id)
    await session.execute(delete(Note).where(Note.id == note_id))
    await session.commit()
```

- [ ] **Step 7: Add paper deletion**

Append to `backend/app/core/papers.py` (existing imports already cover `asyncio`, `Path`, `uuid`, `AsyncSession`):

```python


async def delete_paper(session: AsyncSession, paper_id: uuid.UUID) -> None:
    """Chunks and note anchors cascade. Notes survive: they are the primary object."""
    paper = await get_paper(session, paper_id)
    await session.delete(paper)
    await session.commit()
    await asyncio.to_thread(Path(paper.file_path).unlink, missing_ok=True)
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd backend && uv run pytest -q`
Expected: `10 passed` (3 chunking + 7 notes).

- [ ] **Step 9: Lint and check the invariant**

Run: `cd backend && uv run ruff check . && grep -r fastapi app/core/ ; echo "grep exit $?"`
Expected: `All checks passed!` and `grep exit 1` (no matches).

- [ ] **Step 10: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/models backend/app/core backend/tests
git commit -m "feat: notes domain with provenance rules and paper deletion"
```

---

### Task 2: Notes and paper-file HTTP API

**Files:**
- Create: `backend/app/api/deps.py`
- Create: `backend/app/schemas/notes.py`
- Modify: `backend/app/schemas/papers.py`
- Modify: `backend/app/core/papers.py` (append `get_paper_file`)
- Create: `backend/app/api/notes.py`
- Rewrite: `backend/app/api/papers.py`
- Modify: `backend/app/api/health.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_notes_api.py`, `backend/tests/test_notes_edges.py` (Step 10a)

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces these HTTP routes. The frontend relies on these exact paths and JSON shapes.

| Route | Request body | Response |
|---|---|---|
| `GET /api/papers/{paper_id}/notes` | none | `NoteOut[]` in reading order |
| `POST /api/notes` | `{"body": str = "", "anchor": {"paper_id", "page" ≥ 1, "bbox": [[x0,y0,x1,y1], ...] (1..500), "quoted_text" (1..20000 chars)}}` | 201 `NoteOut` |
| `PATCH /api/notes/{note_id}` | `{"body": str}` | `NoteOut` |
| `DELETE /api/notes/{note_id}` | none | 204 |
| `GET /api/papers/{paper_id}/file` | none | `application/pdf`; 404 if the paper or its file is missing |
| `DELETE /api/papers/{paper_id}` | none | 204 |

`NoteOut` is `{id, body, provenance: "human"|"llm"|"llm_edited", source_id, created_at, updated_at, anchors: [{paper_id, page, bbox, quoted_text}]}`.
- `app.schemas.papers.Rect = tuple[float, float, float, float]`
- `app.api.deps.SessionDep`

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/test_notes_api.py`:

```python
import uuid

import pytest

from app.models import Paper

pytestmark = pytest.mark.anyio


async def make_paper(session, file_path: str, page_count=2) -> Paper:
    paper = Paper(title="api paper", file_path=file_path, page_count=page_count)
    session.add(paper)
    await session.commit()
    return paper


async def test_note_lifecycle_over_http(client, session, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    paper = await make_paper(session, str(pdf))

    pdf_response = await client.get(f"/api/papers/{paper.id}/file")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"

    anchor = {"paper_id": str(paper.id), "page": 2, "bbox": [[10, 20, 30, 40]], "quoted_text": "self-atten-\ntion"}
    created = await client.post("/api/notes", json={"body": "key claim", "anchor": anchor})
    assert created.status_code == 201
    note = created.json()
    assert note["provenance"] == "human"
    assert note["anchors"] == [
        {"paper_id": str(paper.id), "page": 2, "bbox": [[10, 20, 30, 40]], "quoted_text": "self-attention"}
    ]

    listed = await client.get(f"/api/papers/{paper.id}/notes")
    assert [n["id"] for n in listed.json()] == [note["id"]]

    patched = await client.patch(f"/api/notes/{note['id']}", json={"body": "revised"})
    assert patched.status_code == 200
    assert patched.json()["body"] == "revised"

    assert (await client.delete(f"/api/notes/{note['id']}")).status_code == 204
    assert (await client.get(f"/api/papers/{paper.id}/notes")).json() == []

    assert (await client.delete(f"/api/papers/{paper.id}")).status_code == 204
    assert (await client.get(f"/api/papers/{paper.id}")).status_code == 404
    assert not pdf.exists()


async def test_note_and_file_errors_map_to_status_codes(client, session):
    paper = await make_paper(session, "/missing.pdf", page_count=1)
    anchor = {"paper_id": str(paper.id), "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "q"}

    bad_rect = await client.post("/api/notes", json={"anchor": {**anchor, "bbox": [[1, 2, 3]]}})
    page_out_of_range = await client.post("/api/notes", json={"anchor": {**anchor, "page": 5}})
    unknown_paper = await client.post("/api/notes", json={"anchor": {**anchor, "paper_id": str(uuid.uuid4())}})
    missing_file = await client.get(f"/api/papers/{paper.id}/file")

    assert bad_rect.status_code == 422
    assert page_out_of_range.status_code == 422
    assert unknown_paper.status_code == 404
    assert missing_file.status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_notes_api.py -q`
Expected: 2 failed. The first fails on `assert 404 == 200` (no file route); the second on `assert 404 == 422` (no notes route).

- [ ] **Step 3: Add the session dependency alias**

Create `backend/app/api/deps.py`:

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```

- [ ] **Step 4: Add the schemas**

In `backend/app/schemas/papers.py`, replace `from pydantic import BaseModel, ConfigDict` with:

```python
from pydantic import BaseModel, ConfigDict

# PDF points, top-left origin: (x0, y0, x1, y1). A tuple so OpenAPI (and the TS types) say 4 numbers.
Rect = tuple[float, float, float, float]
```

In `ChunkOut` in the same file, replace `bbox: list[list[float]]` with `bbox: list[Rect]`.

Create `backend/app/schemas/notes.py`:

```python
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.papers import Rect


class AnchorIn(BaseModel):
    paper_id: uuid.UUID
    page: int = Field(ge=1)
    bbox: list[Rect] = Field(min_length=1, max_length=500)
    quoted_text: str = Field(min_length=1, max_length=20_000)


class AnchorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paper_id: uuid.UUID
    page: int
    bbox: list[Rect]
    quoted_text: str


class NoteCreate(BaseModel):
    body: str = Field(default="", max_length=50_000)
    anchor: AnchorIn


class NoteUpdate(BaseModel):
    body: str = Field(max_length=50_000)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    provenance: Literal["human", "llm", "llm_edited"]
    source_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    anchors: list[AnchorOut]
```

- [ ] **Step 5: Add file lookup to the papers service**

Append to `backend/app/core/papers.py`:

```python


async def get_paper_file(session: AsyncSession, paper_id: uuid.UUID) -> Path:
    path = Path((await get_paper(session, paper_id)).file_path)
    if not path.is_file():
        raise NotFound(f"PDF for paper {paper_id} is missing from storage")
    return path
```

- [ ] **Step 6: Add the notes router**

Create `backend/app/api/notes.py`:

```python
import uuid

from fastapi import APIRouter, Response

from app.api.deps import SessionDep
from app.core import notes
from app.schemas.notes import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(tags=["notes"])


@router.get("/api/papers/{paper_id}/notes")
async def list_paper_notes(paper_id: uuid.UUID, session: SessionDep) -> list[NoteOut]:
    return await notes.list_notes_for_paper(session, paper_id)


@router.post("/api/notes", status_code=201)
async def create_note(payload: NoteCreate, session: SessionDep) -> NoteOut:
    return await notes.create_human_note(session, payload.body, notes.Anchor(**payload.anchor.model_dump()))


@router.patch("/api/notes/{note_id}")
async def update_note(note_id: uuid.UUID, payload: NoteUpdate, session: SessionDep) -> NoteOut:
    return await notes.update_note_body(session, note_id, payload.body)


@router.delete("/api/notes/{note_id}", status_code=204)
async def delete_note(note_id: uuid.UUID, session: SessionDep) -> Response:
    await notes.delete_note(session, note_id)
    return Response(status_code=204)
```

- [ ] **Step 7: Rewrite the papers router**

Replace `backend/app/api/papers.py` with:

```python
import uuid

from fastapi import APIRouter, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import SessionDep
from app.config import settings
from app.core import papers
from app.schemas.papers import ChunkOut, PaperOut

router = APIRouter(prefix="/api/papers", tags=["papers"])


async def _enqueue_ingest(request: Request, paper_id: uuid.UUID) -> None:
    await request.app.state.arq.enqueue_job("ingest_paper", str(paper_id))


@router.post("", status_code=201)
async def upload_paper(file: UploadFile, request: Request, session: SessionDep) -> PaperOut:
    paper = await papers.create_paper(session, file.filename or "untitled.pdf", await file.read(), settings.pdf_dir)
    await _enqueue_ingest(request, paper.id)
    return paper


@router.get("")
async def list_papers(session: SessionDep) -> list[PaperOut]:
    return await papers.list_papers(session)


@router.get("/{paper_id}")
async def get_paper(paper_id: uuid.UUID, session: SessionDep) -> PaperOut:
    return await papers.get_paper(session, paper_id)


@router.delete("/{paper_id}", status_code=204)
async def delete_paper(paper_id: uuid.UUID, session: SessionDep) -> Response:
    await papers.delete_paper(session, paper_id)
    return Response(status_code=204)


@router.get("/{paper_id}/file", response_class=FileResponse)
async def get_paper_file(paper_id: uuid.UUID, session: SessionDep) -> FileResponse:
    return FileResponse(await papers.get_paper_file(session, paper_id), media_type="application/pdf")


@router.get("/{paper_id}/chunks")
async def list_chunks(paper_id: uuid.UUID, session: SessionDep, page: int | None = None) -> list[ChunkOut]:
    return await papers.list_chunks(session, paper_id, page)


@router.post("/{paper_id}/reingest", status_code=202)
async def reingest_paper(paper_id: uuid.UUID, request: Request, session: SessionDep) -> PaperOut:
    paper = await papers.get_paper(session, paper_id)
    await _enqueue_ingest(request, paper.id)
    return paper
```

- [ ] **Step 8: Switch the health route to SessionDep**

In `backend/app/api/health.py`, replace the import block:

```python
from fastapi import APIRouter, Depends
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import Chunk, Paper
```

with:

```python
from fastapi import APIRouter
from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, select, text

from app.api.deps import SessionDep
from app.config import settings
from app.models import Chunk, Paper
```

Then replace `async def health(session: AsyncSession = Depends(get_session)) -> dict:` with `async def health(session: SessionDep) -> dict:`.

- [ ] **Step 9: Mount the notes router**

In `backend/app/main.py`, replace `from app.api import health, papers` with `from app.api import health, notes, papers`. Below `app.include_router(papers.router)`, add `app.include_router(notes.router)`.

- [ ] **Step 10: Run all backend tests**

Run: `cd backend && uv run pytest -q`
Expected: `12 passed`.

- [ ] **Step 10a: Cover the remaining error branches**

The Task 1 and Task 2 tests cover the happy paths and the main errors. This file adds the branches they leave out, so every route and core function has its error paths tested (testing rule 3). The code already exists, so these pass on the first run; **a failure here means Task 1 or 2 has a bug**, not that the test is wrong.

Create `backend/tests/test_notes_edges.py`:

```python
"""Branches the M3 happy-path tests leave uncovered: empty quotes, repeated LLM edits, unknown ids."""

import uuid

import pytest

from app.core import notes
from app.core.errors import InvalidInput
from app.models import Note, Paper, Provenance

pytestmark = pytest.mark.anyio


async def test_whitespace_only_quote_is_rejected(session):
    paper = Paper(title="edge paper", file_path="/nonexistent.pdf", page_count=1)
    session.add(paper)
    await session.commit()

    with pytest.raises(InvalidInput):
        await notes.create_human_note(session, "", notes.Anchor(paper.id, 1, [(1.0, 2.0, 3.0, 4.0)], "  \n "))


async def test_llm_edited_note_stays_llm_edited_on_later_edits(session):
    note = Note(body="model said", provenance=Provenance.LLM)
    session.add(note)
    await session.commit()

    await notes.update_note_body(session, note.id, "edit one")
    assert (await notes.update_note_body(session, note.id, "edit two")).provenance == Provenance.LLM_EDITED


async def test_unknown_ids_are_404_on_every_notes_route(client):
    missing = uuid.uuid4()
    assert (await client.get(f"/api/papers/{missing}/notes")).status_code == 404
    assert (await client.patch(f"/api/notes/{missing}", json={"body": "x"})).status_code == 404
    assert (await client.delete(f"/api/notes/{missing}")).status_code == 404
    assert (await client.delete(f"/api/papers/{missing}")).status_code == 404


async def test_blank_quote_over_http_is_422(client, session):
    paper = Paper(title="edge paper", file_path="/nonexistent.pdf", page_count=1)
    session.add(paper)
    await session.commit()
    anchor = {"paper_id": str(paper.id), "page": 1, "bbox": [[1, 2, 3, 4]], "quoted_text": "   "}

    assert (await client.post("/api/notes", json={"anchor": anchor})).status_code == 422
```

Run: `cd backend && uv run pytest tests/test_notes_edges.py -q`
Expected: `4 passed`.

If `main` already has the M1–M2 test pack with the coverage gate (roadmap D21), also run `cd backend && uv run pytest --cov` in a checkout that includes it. Expected: `Required test coverage of 80% reached`. Task 7 enforces this before the branch is finished.

- [ ] **Step 11: Lint, check the invariant, and check the live API**

The api container reloads from the worktree mount.

```bash
cd backend && uv run ruff check . && (grep -r fastapi app/core/ || echo "core clean")
curl -s localhost:8000/openapi.json | python3 -c "import sys,json; print(sorted(json.load(sys.stdin)['paths']))"
```

Expected: `All checks passed!`, `core clean`, and paths including `/api/notes`, `/api/notes/{note_id}`, `/api/papers/{paper_id}/file`, `/api/papers/{paper_id}/notes`.

- [ ] **Step 12: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: notes API, paper file and delete routes"
```

---

### Task 3: Frontend scaffold, typed client, library page

> **Styling here is superseded.** This task was built before D24. Task 4.5 replaces the hand-written `index.css` tokens, `library.css`, and the `useState`/`fetch` data loading in `LibraryPage.tsx` with shadcn/ui, Tailwind and TanStack Query. The routing, API client, E2E harness and library spec from this task stay as they are.

**Files:**
- Create: `frontend/` (scaffolded), `frontend/Dockerfile`, `frontend/.dockerignore`
- Modify: `frontend/package.json`, `frontend/index.html`, `docker-compose.yml`, `README.md`
- Rewrite: `frontend/vite.config.ts`, `frontend/src/index.css`, `frontend/src/App.tsx`
- Create: `frontend/src/api/client.ts`, `frontend/src/api/schema.d.ts` (generated), `frontend/src/lib/route.ts`, `frontend/src/features/library/LibraryPage.tsx`, `frontend/src/features/library/library.css`
- Create (E2E harness): `frontend/playwright.config.ts`, `frontend/tsconfig.e2e.json`, `frontend/e2e/fixtures.ts`, `frontend/e2e/fixtures/make_sample_paper.py`, `frontend/e2e/fixtures/sample-paper.pdf` (generated)
- Modify: `frontend/.gitignore`
- Test: `frontend/src/lib/route.test.ts`, `frontend/e2e/library.spec.ts`

**Interfaces:**
- Consumes: the Task 2 HTTP routes and the existing `GET/POST /api/papers`.
- Produces:
  - `api` object (`frontend/src/api/client.ts`): `listPapers()`, `getPaper(id)`, `uploadPaper(file)`, `deletePaper(id)`, `paperFileUrl(id): string`, `listNotes(paperId)`, `createNote(NoteCreate)`, `updateNote(id, body)`, `deleteNote(id)`.
  - Types `Paper`, `Chunk`, `Note`, `NoteCreate` (from generated `components['schemas']`).
  - `frontend/src/lib/route.ts`: `Route = {name:'library'} | {name:'reader', paperId}`, `parseRoute(hash)`, `readerHref(paperId)`, `useRoute()`.
  - CSS tokens in `index.css`: `--bg --surface --text --muted --border --accent --ok --danger`; classes `.button .button-primary .link-button .error`.
  - E2E harness in `frontend/e2e/fixtures.ts`, used by Tasks 5 and 6:
    - `test` with a `paperId` fixture: a freshly ingested fixture paper, deleted after the test.
    - `expect`, `FIXTURE_FILE`, `FIXTURE_TITLE` (`'PaperLab E2E Fixture'`), `FIRST_LINE` (`'Highlights are the anchor'`), `type Rect`.
    - `removePaperAndNotes(request, paperId)`.
    - `openReader(page, paperId): Promise<Locator>` (page 1's first text-layer line).
    - `selectText(start, end?)`, `saveNoteOn(page, line, body): Promise<Locator>` (the note card), `boxOffset(a, b): Promise<number>`.

- [ ] **Step 1: Scaffold with create-vite**

Run from the worktree root. Use a relative directory name: an absolute path makes create-vite create nested directories in the current folder.

```bash
npm create vite@9.2.1 frontend -- --template react-ts --no-interactive
cd frontend
rm -rf src/App.css src/assets public/icons.svg
npm pkg set name=paperlab-frontend
sed -i '' 's#<title>frontend</title>#<title>PaperLab</title>#' index.html
npm install
npm install pdfjs-dist@6.3.289
npm install -D vitest@5.0.0 @playwright/test@1.63.0
npm pkg set scripts.test="vitest run" scripts.e2e="playwright test" scripts.prebuild="npm run gen:api"
npm pkg set scripts.typecheck:e2e="tsc -p tsconfig.e2e.json"
npm pkg set scripts.gen:api='npx --yes openapi-typescript@7.13.0 "${API_URL:-http://localhost:8000}/openapi.json" -o src/api/schema.d.ts'
```

On Linux, use `sed -i` without `''`. Expected: `grep -c '<title>PaperLab</title>' index.html` prints `1`.

- [ ] **Step 2: Configure Vite (proxy + Vitest)**

Replace `frontend/vite.config.ts` with:

```ts
/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // API_URL is http://api:8000 inside compose; the host default is for `npm run dev` on the host.
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
  test: { include: ['src/**/*.test.ts'] },
})
```

- [ ] **Step 3: Write the failing route test**

Create `frontend/src/lib/route.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { parseRoute, readerHref } from './route'

describe('parseRoute', () => {
  it('opens the reader for a paper id', () => {
    const id = '1f0e7570-3249-4d59-aa5c-8f9a03c2b70a'
    expect(parseRoute(readerHref(id))).toEqual({ name: 'reader', paperId: id })
  })

  it('falls back to the library for anything else', () => {
    expect(parseRoute('')).toEqual({ name: 'library' })
    expect(parseRoute('#/')).toEqual({ name: 'library' })
    expect(parseRoute('#/papers/not-an-id')).toEqual({ name: 'library' })
  })
})
```

- [ ] **Step 4: Run it to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL, `Failed to resolve import "./route"`.

- [ ] **Step 5: Implement routing**

Create `frontend/src/lib/route.ts`:

```ts
import { useSyncExternalStore } from 'react'

export type Route = { name: 'library' } | { name: 'reader'; paperId: string }

const READER_HASH = /^#\/papers\/([0-9a-f-]{36})$/i

export function parseRoute(hash: string): Route {
  const match = READER_HASH.exec(hash)
  return match ? { name: 'reader', paperId: match[1] } : { name: 'library' }
}

export const readerHref = (paperId: string) => `#/papers/${paperId}`

function subscribe(onChange: () => void) {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

// ponytail: hash routing covers two views; adopt a router once routes need more than an id.
export function useRoute(): Route {
  return parseRoute(useSyncExternalStore(subscribe, () => window.location.hash))
}
```

Run: `cd frontend && npm test`
Expected: `Tests  2 passed (2)`.

- [ ] **Step 6: Generate API types and write the client**

Run: `cd frontend && npm run gen:api && grep -c '"human" | "llm" | "llm_edited"' src/api/schema.d.ts`
Expected: `🚀 http://localhost:8000/openapi.json → src/api/schema.d.ts`, then `1`.

Create `frontend/src/api/client.ts`:

```ts
import type { components } from './schema'

export type Paper = components['schemas']['PaperOut']
export type Chunk = components['schemas']['ChunkOut']
export type Note = components['schemas']['NoteOut']
export type NoteCreate = components['schemas']['NoteCreate']

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const detail: unknown = await response.json().then((body) => body.detail, () => response.statusText)
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

const sendJson = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  listPapers: () => request<Paper[]>('/api/papers'),
  getPaper: (id: string) => request<Paper>(`/api/papers/${id}`),
  uploadPaper: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Paper>('/api/papers', { method: 'POST', body: form })
  },
  deletePaper: (id: string) => request<void>(`/api/papers/${id}`, { method: 'DELETE' }),
  paperFileUrl: (id: string) => `/api/papers/${id}/file`,
  listNotes: (paperId: string) => request<Note[]>(`/api/papers/${paperId}/notes`),
  createNote: (note: NoteCreate) => request<Note>('/api/notes', sendJson('POST', note)),
  updateNote: (id: string, body: string) => request<Note>(`/api/notes/${id}`, sendJson('PATCH', { body })),
  deleteNote: (id: string) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
}
```

- [ ] **Step 7: Base styles**

Replace `frontend/src/index.css` with:

```css
:root {
  color-scheme: light;
  --bg: #f6f5f1;
  --surface: #ffffff;
  --text: #1d1d1f;
  --muted: #6b6b70;
  --border: #dcdad3;
  --accent: #2f5bd3;
  --ok: #1e7a3a;
  --danger: #b3261e;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  font-size: 15px;
  color: var(--text);
  background: var(--bg);
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: 0;
}

button,
.button {
  font: inherit;
  cursor: pointer;
  color: var(--text);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.35rem 0.75rem;
}

button:disabled {
  cursor: default;
  opacity: 0.5;
}

.button-primary {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
}

.link-button {
  color: var(--muted);
  background: none;
  border: none;
  padding: 0;
  text-decoration: none;
}

.error {
  color: var(--danger);
}
```

- [ ] **Step 8: Library page**

Create `frontend/src/features/library/LibraryPage.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { api, type Paper } from '../../api/client'
import { readerHref } from '../../lib/route'
import './library.css'

const POLL_MS = 2000
const isSettled = (paper: Paper) => paper.status === 'ready' || paper.status === 'failed'

export function LibraryPage() {
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const refresh = useCallback(
    () => api.listPapers().then(setPapers, (e: Error) => setError(e.message)),
    [],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll only while something is still ingesting.
  const ingesting = papers?.some((paper) => !isSettled(paper)) ?? false
  useEffect(() => {
    if (!ingesting) return
    const timer = setInterval(refresh, POLL_MS)
    return () => clearInterval(timer)
  }, [ingesting, refresh])

  async function upload(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length === 0) return
    setUploading(true)
    setError(null)
    try {
      for (const file of files) await api.uploadPaper(file)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
      await refresh()
    }
  }

  async function remove(paper: Paper) {
    if (!window.confirm(`Delete "${paper.title}"? Its highlights go with it; notes are kept.`)) return
    try {
      await api.deletePaper(paper.id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <main className="library">
      <header className="library-header">
        <h1>PaperLab</h1>
        <label className="button button-primary">
          {uploading ? 'Uploading…' : 'Upload PDFs'}
          <input
            type="file"
            accept="application/pdf"
            multiple
            hidden
            disabled={uploading}
            onChange={(e) => void upload(e.currentTarget)}
          />
        </label>
      </header>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}

      {papers === null ? (
        <p>Loading…</p>
      ) : papers.length === 0 ? (
        <p>No papers yet. Upload a PDF to start.</p>
      ) : (
        <ul className="paper-list">
          {papers.map((paper) => (
            <li key={paper.id} className="paper-row">
              <a href={readerHref(paper.id)}>{paper.title}</a>
              <span className={`status status-${paper.status}`}>{paper.status}</span>
              <button type="button" className="link-button" onClick={() => void remove(paper)}>
                Delete
              </button>
              {paper.status_error && <small className="error">{paper.status_error}</small>}
            </li>
          ))}
        </ul>
      )}
    </main>
  )
}
```

Create `frontend/src/features/library/library.css`:

```css
.library {
  max-width: 860px;
  margin: 0 auto;
  padding: 1.5rem 1rem;
}

.library-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.paper-list {
  list-style: none;
  margin: 0;
  padding: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.paper-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 0.25rem 1rem;
  align-items: center;
  padding: 0.7rem 1rem;
  border-top: 1px solid var(--border);
}

.paper-row:first-child {
  border-top: none;
}

.paper-row a {
  color: var(--text);
  font-weight: 500;
  text-decoration: none;
}

.paper-row small {
  grid-column: 1 / -1;
}

.status {
  font-size: 0.8rem;
  color: var(--muted);
}

.status-ready {
  color: var(--ok);
}

.status-failed {
  color: var(--danger);
}
```

Replace `frontend/src/App.tsx` with this Task 3 version (Task 5 replaces it):

```tsx
import { LibraryPage } from './features/library/LibraryPage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  // The reader lands in Task 5; until then a paper link shows this.
  if (route.name === 'reader') return <p className="library">Reader coming next. <a href="#/">Back to library</a></p>
  return <LibraryPage />
}
```

Leave `frontend/src/main.tsx` as the template generated it.

- [ ] **Step 9: Containerize and add to compose**

Create `frontend/Dockerfile`:

```dockerfile
FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

Create `frontend/.dockerignore`:

```
node_modules
dist
test-results
playwright-report
```

In `docker-compose.yml`, add this service after `worker:` (inside `services:`):

```yaml
  frontend:
    build: ./frontend
    environment:
      API_URL: http://api:8000
    ports: ["5180:5173"]
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on: [api]
```

Run: `docker compose up -d --build frontend`

- [ ] **Step 10: Verify the app builds and is served**

```bash
cd frontend && npx tsc -b && npm test
curl -s -o /dev/null -w "%{http_code}\n" localhost:5180/
curl -s localhost:5180/api/papers | head -c 80; echo
```

Expected:
- `tsc` prints nothing.
- `Tests  2 passed (2)`.
- `200`.
- A JSON array through the Vite proxy.

- [ ] **Step 11: End-to-end harness**

Every later task adds Playwright specs on top of this harness.

Create `frontend/e2e/fixtures/make_sample_paper.py`:

```python
"""Regenerates sample-paper.pdf: two pages, one heading and one paragraph each.

Run with the backend environment (it has PyMuPDF):
  cd backend && uv run python ../frontend/e2e/fixtures/make_sample_paper.py ../frontend/e2e/fixtures/sample-paper.pdf
"""

import sys

import pymupdf

INTRO = (
    "Highlights are the anchor for every note in PaperLab. A note keeps the exact page and "
    "region of the passage it came from, so a citation can always jump back to the source. "
    "This paragraph exists so the end-to-end test has real, selectable text to work with."
)
METHOD = (
    "The second page describes a method in enough words to form its own chunk. Coordinates are "
    "stored in PDF points with a top-left origin and converted to screen pixels only at render time."
)

doc = pymupdf.open()
for heading, body in [("1 Introduction", INTRO), ("2 Method", METHOD)]:
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 90), heading, fontsize=14, fontname="Times-Bold")
    page.insert_textbox(pymupdf.Rect(72, 110, 540, 300), body, fontsize=11, fontname="Times-Roman")
doc.set_metadata({"title": "PaperLab E2E Fixture"})
doc.save(sys.argv[1])
```

Run: `cd backend && uv run python ../frontend/e2e/fixtures/make_sample_paper.py ../frontend/e2e/fixtures/sample-paper.pdf && ls -l ../frontend/e2e/fixtures/sample-paper.pdf`
Expected: a file of roughly 2 KB.

Create `frontend/playwright.config.ts`:

```ts
import { defineConfig } from '@playwright/test'

// Runs against the real stack: `docker compose up -d` first. No mocked backend.
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  // One real backend and one shared library: run specs one at a time.
  workers: 1,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5180',
    // Fail a stuck action in seconds, so a broken UI fails fast and fixtures still clean up.
    actionTimeout: 10_000,
    trace: 'retain-on-failure',
  },
})
```

Create `frontend/tsconfig.e2e.json`. Playwright strips types without checking them, so this is the only thing that catches a type error in a spec:

```json
{
  "compilerOptions": {
    "target": "es2023",
    "lib": ["ES2023", "DOM"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "types": ["node"],
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "verbatimModuleSyntax": true,
    "noUnusedLocals": true
  },
  "include": ["e2e", "playwright.config.ts"]
}
```

Create `frontend/e2e/fixtures.ts`:

```ts
import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { test as base, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'

export { expect }

export const FIXTURE_FILE = fileURLToPath(new URL('./fixtures/sample-paper.pdf', import.meta.url))
export const FIXTURE_TITLE = 'PaperLab E2E Fixture'
export const FIRST_LINE = 'Highlights are the anchor'
export type Rect = [number, number, number, number]

async function uploadAndWaitUntilReady(request: APIRequestContext): Promise<string> {
  const upload = await request.post('/api/papers', {
    multipart: {
      file: { name: 'sample-paper.pdf', mimeType: 'application/pdf', buffer: await readFile(FIXTURE_FILE) },
    },
  })
  expect(upload.status()).toBe(201)
  const { id } = await upload.json()
  await expect
    .poll(async () => (await (await request.get(`/api/papers/${id}`)).json()).status, { timeout: 30_000 })
    .toBe('ready')
  return id
}

export async function removePaperAndNotes(request: APIRequestContext, paperId: string) {
  const notes = await request.get(`/api/papers/${paperId}/notes`)
  if (!notes.ok()) return // already deleted
  // Notes deliberately survive paper deletion, so remove them first.
  for (const note of await notes.json()) await request.delete(`/api/notes/${note.id}`)
  await request.delete(`/api/papers/${paperId}`)
}

/** `paperId`: a freshly ingested copy of the fixture paper, removed after the test even if it fails. */
export const test = base.extend<{ paperId: string }>({
  paperId: async ({ request }, use) => {
    const id = await uploadAndWaitUntilReady(request)
    await use(id)
    await removePaperAndNotes(request, id)
  },
})

/** Opens the reader and returns page 1's first text-layer line once it is rendered. */
export async function openReader(page: Page, paperId: string): Promise<Locator> {
  await page.goto(`/#/papers/${paperId}`)
  const line = page.locator('.pdf-page[data-page="1"] .textLayer span', { hasText: FIRST_LINE })
  await expect(line).toBeVisible()
  return line
}

/** Selects from the start of `start` to the end of `end` like a mouse drag, then releases the mouse. */
export async function selectText(start: Locator, end: Locator = start) {
  const endElement = await end.elementHandle()
  await start.evaluate((from, to) => {
    const range = document.createRange()
    range.setStart(from.firstChild!, 0)
    range.setEnd(to!.firstChild!, to!.textContent!.length)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
  }, endElement)
  await start.dispatchEvent('mouseup')
}

export async function saveNoteOn(page: Page, line: Locator, body: string): Promise<Locator> {
  await selectText(line)
  await page.getByRole('textbox', { name: 'Note' }).fill(body)
  await page.getByRole('button', { name: 'Save note' }).click()
  const card = page.locator('article.note', { hasText: body })
  await expect(card).toBeVisible()
  return card
}

/** Largest offset in px between two elements' boxes; retried by callers while layout settles. */
export async function boxOffset(a: Locator, b: Locator): Promise<number> {
  const [boxA, boxB] = [await a.boundingBox(), await b.boundingBox()]
  if (!boxA || !boxB) return Number.POSITIVE_INFINITY
  return Math.max(Math.abs(boxA.x - boxB.x), Math.abs(boxA.y - boxB.y), Math.abs(boxA.width - boxB.width))
}
```

Append to `frontend/.gitignore`:

```
test-results
playwright-report
```

Run: `cd frontend && npx playwright install chromium && npm run typecheck:e2e`
Expected: Chromium installs; `tsc -p tsconfig.e2e.json` prints no errors.

- [ ] **Step 12: Library E2E spec**

Create `frontend/e2e/library.spec.ts`:

```ts
import { FIXTURE_FILE, FIXTURE_TITLE, expect, removePaperAndNotes, test } from './fixtures'

test('upload a PDF through the UI, watch it become ready, then delete it', async ({ page, request }) => {
  await page.goto('/')
  const [uploaded] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/api/papers') && r.request().method() === 'POST'),
    page.locator('input[type="file"]').setInputFiles(FIXTURE_FILE),
  ])
  const { id } = await uploaded.json()

  try {
    const row = page.locator('.paper-row').filter({ has: page.locator(`a[href="#/papers/${id}"]`) })
    // The library polls while ingesting; the title switches from the file name to the PDF's metadata title.
    await expect(row.locator('.status')).toHaveText('ready', { timeout: 30_000 })
    await expect(row.getByRole('link')).toHaveText(FIXTURE_TITLE)

    page.once('dialog', (dialog) => dialog.accept())
    await row.getByRole('button', { name: 'Delete' }).click()
    await expect(row).toHaveCount(0)
    expect((await request.get(`/api/papers/${id}`)).status()).toBe(404)
  } finally {
    await removePaperAndNotes(request, id)
  }
})

test('a non-PDF upload shows the error and creates no paper', async ({ page, request }) => {
  await page.goto('/')
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name: 'not-a-paper.txt', mimeType: 'text/plain', buffer: Buffer.from('plain text') })

  await expect(page.getByRole('alert')).toContainText('is not a PDF')
  const papers: { title: string }[] = await (await request.get('/api/papers')).json()
  expect(papers.some((p) => p.title === 'not-a-paper')).toBe(false)
})
```

Run: `cd frontend && npm run typecheck:e2e && npm run e2e`
Expected: no type errors; `2 passed`.

- [ ] **Step 13: Prove the library spec catches a broken library**

The page was built before the spec, so the spec couldn't be red first. Break the page on purpose instead:
1. In `frontend/src/features/library/LibraryPage.tsx`, replace `if (!ingesting) return` with `return`. The library now never polls.
2. Run: `cd frontend && npx playwright test -g "upload a PDF through the UI"`
   Expected: `1 failed`, because the status never shows `ready`.
3. Undo the edit and run the same command again.
   Expected: `1 passed`.

- [ ] **Step 14: Document the commands**

Replace `README.md` with:

````markdown
# PaperLab

Local-first research reading tool. Plan: [docs/superpowers/plans/2026-09-13-paperlab-roadmap.md](docs/superpowers/plans/2026-09-13-paperlab-roadmap.md)

```sh
cp .env.example .env
docker compose up -d --build          # db (:5433), redis, api (:8000), worker, frontend (:5180)
open http://localhost:5180

curl localhost:8000/api/health        # vector round-trip through ORM and raw SQL
curl -X POST localhost:8000/api/papers/<id>/reingest     # idempotent re-run after changing chunking

cd backend && uv run pytest && uv run ruff check .       # needs the compose db
cd frontend && npm run gen:api                           # regenerate API types (api running)
cd frontend && npx tsc -b && npm test                    # types + unit tests
cd frontend && npx playwright install chromium            # once
cd frontend && npm run typecheck:e2e && npm run e2e      # end-to-end against the running stack
```
````

- [ ] **Step 15: Commit**

```bash
git add frontend docker-compose.yml README.md
git status --short frontend | grep node_modules && echo "STOP: node_modules staged" || true
git commit -m "feat: frontend scaffold with typed API client and library page"
```

---

### Task 4: Reader coordinate conversions

The brief's "three coordinate systems" trap, as pure functions with tests.

**Files:**
- Create: `frontend/src/features/reader/coords.ts`
- Test: `frontend/src/features/reader/coords.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `type PdfRect = [x0, y0, x1, y1]`
  - `type CssBox = {left, top, width, height}`
  - `type ClientRectLike = {left, top, right, bottom}`
  - `pdfRectToCss(rect: PdfRect, scale: number): CssBox`
  - `mergeLines(rects: PdfRect[]): PdfRect[]`
  - `clientRectsToPdfRects(rects: ClientRectLike[], page: ClientRectLike, scale: number): PdfRect[]`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/features/reader/coords.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { clientRectsToPdfRects, mergeLines, pdfRectToCss, type PdfRect } from './coords'

describe('pdfRectToCss', () => {
  it('scales PDF points to CSS pixels', () => {
    expect(pdfRectToCss([72, 400, 290, 410], 1.5)).toEqual({ left: 108, top: 600, width: 327, height: 15 })
  })
})

describe('mergeLines', () => {
  it('merges word boxes on one line but keeps separate lines and columns apart', () => {
    const words: PdfRect[] = [
      [100, 400, 130, 410], // line 1, second word (out of order)
      [72, 400, 98, 410], // line 1, first word
      [72, 412, 200, 422], // line 2
      [310, 400, 400, 410], // same height as line 1, but in the right-hand column
    ]
    expect(mergeLines(words)).toEqual([
      [72, 400, 130, 410],
      [310, 400, 400, 410],
      [72, 412, 200, 422],
    ])
  })
})

describe('clientRectsToPdfRects', () => {
  it('converts viewport pixels relative to the page into rounded PDF points', () => {
    const page = { left: 50, top: 1000, right: 943, bottom: 2263 }
    const selection = [
      { left: 158, top: 1600, right: 250, bottom: 1615 },
      { left: 251, top: 1600, right: 485, bottom: 1615 },
      { left: 60, top: 1010, right: 60, bottom: 1030 }, // zero-width caret box: ignored
    ]
    expect(clientRectsToPdfRects(selection, page, 1.5)).toEqual([[72, 400, 290, 410]])
  })

  it('round-trips with pdfRectToCss at any zoom', () => {
    const stored: PdfRect = [72.5, 409.25, 290.27, 420.13]
    for (const scale of [0.75, 1, 2.5]) {
      const css = pdfRectToCss(stored, scale)
      const client = { left: css.left, top: css.top, right: css.left + css.width, bottom: css.top + css.height }
      expect(clientRectsToPdfRects([client], { left: 0, top: 0, right: 0, bottom: 0 }, scale)).toEqual([stored])
    }
  })
})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL, `Failed to resolve import "./coords"`.

- [ ] **Step 3: Implement**

Create `frontend/src/features/reader/coords.ts`:

```ts
/**
 * Three coordinate systems meet in the reader:
 * - PDF points, top-left origin: what the backend stores (PyMuPDF) and the only thing we persist.
 * - CSS pixels inside a rendered page: PDF points × scale.
 * - Viewport pixels from the DOM (getClientRects): CSS pixels offset by the page's position.
 * Convert at render time; never store anything but PDF points.
 */

export type PdfRect = [x0: number, y0: number, x1: number, y1: number]
export type CssBox = { left: number; top: number; width: number; height: number }
export type ClientRectLike = { left: number; top: number; right: number; bottom: number }

// Word boxes closer than this (in points) on the same line merge; column gaps are wider.
const SAME_LINE_GAP_PT = 6

export function pdfRectToCss([x0, y0, x1, y1]: PdfRect, scale: number): CssBox {
  return { left: x0 * scale, top: y0 * scale, width: (x1 - x0) * scale, height: (y1 - y0) * scale }
}

function onSameLine(a: PdfRect, b: PdfRect): boolean {
  const verticalOverlap = Math.min(a[3], b[3]) - Math.max(a[1], b[1])
  const smallerHeight = Math.min(a[3] - a[1], b[3] - b[1])
  const horizontalGap = Math.max(a[0], b[0]) - Math.min(a[2], b[2])
  return verticalOverlap >= smallerHeight / 2 && horizontalGap <= SAME_LINE_GAP_PT
}

export function mergeLines(rects: PdfRect[]): PdfRect[] {
  const sorted = [...rects].sort((a, b) => a[1] - b[1] || a[0] - b[0])
  return sorted.reduce<PdfRect[]>((lines, rect) => {
    const index = lines.findIndex((line) => onSameLine(line, rect))
    if (index === -1) return [...lines, rect]
    const line = lines[index]
    const merged: PdfRect = [
      Math.min(line[0], rect[0]),
      Math.min(line[1], rect[1]),
      Math.max(line[2], rect[2]),
      Math.max(line[3], rect[3]),
    ]
    return lines.map((existing, i) => (i === index ? merged : existing))
  }, [])
}

export function clientRectsToPdfRects(rects: ClientRectLike[], page: ClientRectLike, scale: number): PdfRect[] {
  const round = (value: number) => Math.round(value * 100) / 100
  const inPoints = rects
    .filter((r) => r.right - r.left > 0.5 && r.bottom - r.top > 0.5)
    .map((r): PdfRect => [
      (r.left - page.left) / scale,
      (r.top - page.top) / scale,
      (r.right - page.left) / scale,
      (r.bottom - page.top) / scale,
    ])
  return mergeLines(inPoints).map(([x0, y0, x1, y1]): PdfRect => [round(x0), round(y0), round(x1), round(y1)])
}
```

- [ ] **Step 4: Run tests and type check**

Run: `cd frontend && npm test && npx tsc -b`
Expected: `Tests  6 passed (6)` and no tsc output.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/reader
git commit -m "feat: reader coordinate conversions between PDF points and DOM pixels"
```

---

### Task 4.5: UI foundation (shadcn/ui, Tailwind, TanStack Query, themes)

Decided after Task 4 was built (roadmap D24, which supersedes D14): the frontend uses shadcn/ui components on Tailwind CSS 4, TanStack Query for API calls, a light/dark theme toggle, and a design system derived from the ui-ux-pro-max skill. This task installs all of it and moves the Library page over. Tasks 5 and 6 then build the reader and notes with it, so no feature ships with hand-written CSS.

**Files:**
- Create: `.mcp.json` (repo root), `frontend/design-system/MASTER.md`, `frontend/components.json` (generated), `frontend/src/components/ui/*` (generated), `frontend/src/lib/utils.ts` (generated)
- Create: `frontend/src/api/queries.ts`, `frontend/src/components/theme-provider.tsx`, `frontend/src/components/mode-toggle.tsx`
- Rewrite: `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/src/index.css`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/features/library/LibraryPage.tsx`
- Modify: `frontend/tsconfig.app.json`, `frontend/package.json`, `frontend/package-lock.json`
- Delete: `frontend/src/features/library/library.css`
- Test: `frontend/e2e/theme.spec.ts`, `frontend/src/api/queries.test.ts`; `frontend/e2e/library.spec.ts` (unchanged) guards the restyled page

**Interfaces:**
- Consumes: the `api` client and types (Task 3); the E2E harness (Task 3).
- Produces:
  - `@/` import alias for `frontend/src`.
  - shadcn components in `@/components/ui/`: `alert`, `badge`, `button`, `card`, `dropdown-menu`, `table`, `textarea`. `cn` from `@/lib/utils`.
  - `frontend/src/api/queries.ts`:
    - `queryClient` (queries don't retry).
    - `usePapers()`, which polls every `PAPERS_POLL_MS` while `papersPollInterval(papers)` says a paper is ingesting.
    - `usePaper(id)`, `useNotes(paperId)`.
    - `useUploadPapers()`, `useDeletePaper()`, which invalidate the papers list.
    - `useNoteMutations(paperId)`: `{create, update, remove}`, which invalidate that paper's notes.
  - `ThemeProvider`, `useTheme()`, and `<ModeToggle />`: a button named "Toggle theme" with menu items Light / Dark / System. The choice is stored in `localStorage` under `paperlab-theme` and applied as the `dark` class on `<html>`.
  - Theme tokens in `src/index.css`: shadcn's (`background`, `primary`, `muted`, …) plus `provenance-llm`, `provenance-llm-foreground`, `provenance-llm-surface`, `highlight`, `highlight-active`, `highlight-draft`.
  - DOM contract kept from Task 3: heading "PaperLab", `input[type="file"]`, `.paper-row` rows with `a[href="#/papers/<id>"]`, `.status` holding the raw status, a "Delete" button with `window.confirm`, errors in `role="alert"`, and a "Retry" button after a failed first load.

- [ ] **Step 1: Write the failing theme spec**

Create `frontend/e2e/theme.spec.ts`:

```ts
import { expect, test } from './fixtures'

test('the theme toggle switches to dark, survives a reload, and "System" follows the OS', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' })
  await page.goto('/')
  const html = page.locator('html')
  await expect(html).not.toHaveClass(/\bdark\b/)

  await page.getByRole('button', { name: 'Toggle theme' }).click()
  await page.getByRole('menuitem', { name: 'Dark' }).click()
  await expect(html).toHaveClass(/\bdark\b/)
  await page.reload()
  await expect(html).toHaveClass(/\bdark\b/)

  await page.getByRole('button', { name: 'Toggle theme' }).click()
  await page.getByRole('menuitem', { name: 'System' }).click()
  await expect(html).not.toHaveClass(/\bdark\b/)
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(html).toHaveClass(/\bdark\b/)
})
```

Run: `cd frontend && npm run typecheck:e2e && npx playwright test e2e/theme.spec.ts`
Expected: no type errors, then `1 failed` with `TimeoutError: locator.click: Timeout 10000ms exceeded`, waiting for the `Toggle theme` button (it doesn't exist yet).

- [ ] **Step 2: Write the failing poll-interval test**

Create `frontend/src/api/queries.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { Paper } from './client'
import { PAPERS_POLL_MS, papersPollInterval } from './queries'

const paper = (status: string) => ({ status }) as Paper

describe('papersPollInterval', () => {
  it('polls while any paper is still ingesting', () => {
    expect(papersPollInterval([paper('ready'), paper('extracting')])).toBe(PAPERS_POLL_MS)
  })

  it('stops once every paper is ready or failed, or before the first load', () => {
    expect(papersPollInterval([paper('ready'), paper('failed')])).toBe(false)
    expect(papersPollInterval(undefined)).toBe(false)
  })
})
```

Run: `cd frontend && npm test`
Expected: FAIL, `Failed to resolve import "./queries"`.

- [ ] **Step 3: Install Tailwind, TanStack Query and the fonts; add the `@` alias**

```bash
cd frontend
npm install tailwindcss@4.3.3 @tailwindcss/vite@4.3.3 @tanstack/react-query@5.102.8 \
  @fontsource-variable/crimson-pro@5.3.0 @fontsource-variable/atkinson-hyperlegible-next@5.3.0
```

Replace `frontend/vite.config.ts` with:

```ts
/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    // API_URL is http://api:8000 inside compose; the host default is for `npm run dev` on the host.
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
  test: { include: ['src/**/*.test.ts'] },
})
```

Replace `frontend/tsconfig.json` with:

```json
{
  "files": [],
  "compilerOptions": { "paths": { "@/*": ["./src/*"] } },
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

In `frontend/tsconfig.app.json`, add this line directly after `"jsx": "react-jsx",`:

```json
    "paths": { "@/*": ["./src/*"] },
```

Don't add `baseUrl`, even though the shadcn guide shows it. TypeScript 6 deprecates it, and `paths` works without it.

- [ ] **Step 4: Initialise shadcn/ui and add the components**

`shadcn init` checks that Tailwind is wired into the stylesheet and fails with `✖ Validating Tailwind CSS` otherwise, so write the import first:

```bash
printf '@import "tailwindcss";\n' > src/index.css
npx --yes shadcn@4.21.0 init -t vite -b radix -p nova --no-monorepo --no-rtl -y < /dev/null
npx --yes shadcn@4.21.0 add alert badge card dropdown-menu table textarea -y
npm uninstall @fontsource-variable/geist
```

Expected:
- `init` prints `✔ Validating Tailwind CSS. Found v4.` and `✔ Validating import alias.`, then creates `components.json`, `src/components/ui/button.tsx` and `src/lib/utils.ts`. It installs `radix-ui`, `class-variance-authority`, `cn` (shadcn's own class-merging package), `lucide-react`, `tw-animate-css` and `shadcn`.
- `add` prints `✔ Created 6 files`.
- The `< /dev/null` stops `init` from waiting on a prompt when run by an agent.
- The Geist font that `init` installs is removed, because the design system uses its own fonts.

- [ ] **Step 5: Design system and theme tokens**

Create `frontend/design-system/MASTER.md`:

````markdown
# PaperLab design system

The single source of truth for how PaperLab looks. Read this before any task that changes what the
UI looks like or how it behaves. If a value here and a value in `src/index.css` disagree, fix
`index.css`.

## Direction

A calm reading tool, in the spirit of Readwise Reader or Zotero 7. The PDF is the content; the
interface around it stays quiet. Desktop first. Light and dark themes, chosen with the toggle
(Light / Dark / System).

Derived from ui-ux-pro-max (`~/.claude/skills/ui-ux-pro-max`), then curated. The generator is tuned
for landing pages, so only these parts of its output were kept:
- Palette: "document grey + scan blue", from
  `search.py "document reader annotation tool minimalism swiss neutral" --design-system`.
- Type pairing: Crimson Pro + Atkinson Hyperlegible ("academic, research, scholarly, accessible"), from
  `search.py "research paper reader note-taking productivity tool calm minimal content-first academic" --design-system`.
- Rejected from its output: landing-page patterns, the mobile touch-first flat style, the OLED-dark-only
  style, and loading fonts from Google (this app is local-first, so fonts are bundled with `@fontsource`).

## Stack

- Components: shadcn/ui, style `radix-nova`, in `src/components/ui/`. Add one with
  `npx shadcn@4.21.0 add <name>` or through the shadcn MCP server (`.mcp.json` at the repo root).
  Never hand-copy a component.
- Styling: Tailwind CSS 4 utility classes. No per-feature `.css` files. The only stylesheets are
  `src/index.css` (tokens) and PDF.js's own `pdf_viewer.css`.
- Icons: `lucide-react` only. Decorative icons get `aria-hidden`; icon-only buttons get `aria-label`.
- Class merging: `cn` from `@/lib/utils`.

## Tokens

Defined in `src/index.css` as CSS variables and exposed to Tailwind through `@theme inline`
(so `bg-primary`, `text-muted-foreground`, `bg-provenance-llm-surface`, …).

| Token | Light | Dark | Use |
|---|---|---|---|
| `background` | `#f8fafc` | `#0f172a` | App background |
| `foreground` | `#0f172a` | `#f1f5f9` | Body text |
| `card` | `#ffffff` | `#1e293b` | Cards, toolbar |
| `primary` / `primary-foreground` | `#2563eb` / `#ffffff` | `#60a5fa` / `#0f172a` | The one primary action per view, focus ring |
| `muted` / `muted-foreground` | `#f1f5f9` / `#475569` | `#1e293b` / `#94a3b8` | Reader pane background, secondary text, quotes |
| `destructive` | `#dc2626` | `#f87171` | Errors, delete |
| `border` / `input` | `#e2e8f0` / `#cbd5e1` | white 10% / white 15% | Dividers, field borders |
| `provenance-llm` / `-foreground` | `#6d28d9` / `#ffffff` | `#a78bfa` / `#1e1b4b` | AI provenance badge |
| `provenance-llm-surface` | `#f5f3ff` | `#2e1065` | AI note card background |
| `highlight` / `-active` / `-draft` | yellow 40% / orange 50% / blue 25% | same | Highlights on the (always white) PDF page |

All text pairs above meet WCAG AA (4.5:1) in their theme. Check any new pair before using it.

Fonts: body `Atkinson Hyperlegible Next Variable` (`font-sans`), headings `Crimson Pro Variable`
(`font-heading`). Radius `0.625rem`.

## PaperLab-specific rules

- **Provenance is never subtle.** Every note shows a `ProvenanceBadge` with an icon and a label
  ("You", "AI", "AI · edited"). AI notes also get the `provenance-llm-surface` background. Never
  rely on colour alone.
- **The PDF page stays white in both themes.** It is the paper. Highlights use `mix-blend-multiply`.
- **Nothing that shifts selection coordinates** goes on `.pdf-page`: no border, no padding.
- **Stable test hooks.** Keep the class names and accessible names the Playwright specs use
  (`.paper-row`, `.status`, `.pdf-page`, `.pdf-overlay`, `.highlight`, `.draft`, `.zoom-level`,
  `article.note`, `.provenance-badge`, the "Note" / "Save note" / "Zoom in" / "Toggle theme" names).
  Style with utility classes next to them.
- One primary button per view. Destructive actions use `text-destructive` and ask for confirmation.

## Pre-delivery check (from ui-ux-pro-max Quick Reference §1–§3)

Run through this before finishing any UI task, in **both** themes:
- [ ] Text contrast ≥ 4.5:1; focus rings visible when tabbing through every control.
- [ ] Every icon-only button has an `aria-label`; every field has a visible or `aria-label` label.
- [ ] Tab order follows the visual order; Escape closes menus and cancels the note draft.
- [ ] Errors appear in an `Alert` (`role="alert"`) near what failed, with a way to recover (Retry, dismiss).
- [ ] Buttons show a pointer cursor and a disabled state while their action runs.
- [ ] No layout shift when data loads; long titles truncate with the full text in `title`.
- [ ] No emoji as icons.
````

Replace `frontend/src/index.css` with:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/atkinson-hyperlegible-next";
@import "@fontsource-variable/crimson-pro";

@custom-variant dark (&:is(.dark *));

/* Theme tokens for PaperLab. Values come from frontend/design-system/MASTER.md; change them there first. */
@theme inline {
    --font-sans: 'Atkinson Hyperlegible Next Variable', ui-sans-serif, system-ui, sans-serif;
    --font-heading: 'Crimson Pro Variable', ui-serif, Georgia, serif;
    --color-background: var(--background);
    --color-foreground: var(--foreground);
    --color-card: var(--card);
    --color-card-foreground: var(--card-foreground);
    --color-popover: var(--popover);
    --color-popover-foreground: var(--popover-foreground);
    --color-primary: var(--primary);
    --color-primary-foreground: var(--primary-foreground);
    --color-secondary: var(--secondary);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-muted: var(--muted);
    --color-muted-foreground: var(--muted-foreground);
    --color-accent: var(--accent);
    --color-accent-foreground: var(--accent-foreground);
    --color-destructive: var(--destructive);
    --color-border: var(--border);
    --color-input: var(--input);
    --color-ring: var(--ring);
    --color-provenance-llm: var(--provenance-llm);
    --color-provenance-llm-foreground: var(--provenance-llm-foreground);
    --color-provenance-llm-surface: var(--provenance-llm-surface);
    --color-highlight: var(--highlight);
    --color-highlight-active: var(--highlight-active);
    --color-highlight-draft: var(--highlight-draft);
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    --background: #f8fafc;
    --foreground: #0f172a;
    --card: #ffffff;
    --card-foreground: #0f172a;
    --popover: #ffffff;
    --popover-foreground: #0f172a;
    --primary: #2563eb;
    --primary-foreground: #ffffff;
    --secondary: #f1f5f9;
    --secondary-foreground: #1e293b;
    --muted: #f1f5f9;
    --muted-foreground: #475569;
    --accent: #f1f5f9;
    --accent-foreground: #1e293b;
    --destructive: #dc2626;
    --border: #e2e8f0;
    --input: #cbd5e1;
    --ring: #2563eb;
    --radius: 0.625rem;
    /* Provenance is never subtle: AI text gets its own badge colour and card background. */
    --provenance-llm: #6d28d9;
    --provenance-llm-foreground: #ffffff;
    --provenance-llm-surface: #f5f3ff;
    /* Highlights are drawn on the white PDF page in both themes. */
    --highlight: rgb(255 212 0 / 0.4);
    --highlight-active: rgb(255 140 0 / 0.5);
    --highlight-draft: rgb(37 99 235 / 0.25);
}

.dark {
    --background: #0f172a;
    --foreground: #f1f5f9;
    --card: #1e293b;
    --card-foreground: #f1f5f9;
    --popover: #1e293b;
    --popover-foreground: #f1f5f9;
    --primary: #60a5fa;
    --primary-foreground: #0f172a;
    --secondary: #1e293b;
    --secondary-foreground: #f1f5f9;
    --muted: #1e293b;
    --muted-foreground: #94a3b8;
    --accent: #334155;
    --accent-foreground: #f1f5f9;
    --destructive: #f87171;
    --border: rgb(255 255 255 / 0.1);
    --input: rgb(255 255 255 / 0.15);
    --ring: #60a5fa;
    --provenance-llm: #a78bfa;
    --provenance-llm-foreground: #1e1b4b;
    --provenance-llm-surface: #2e1065;
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
  html {
    @apply font-sans;
  }
  button:not(:disabled),
  [role="menuitem"] {
    cursor: pointer;
  }
}
```

- [ ] **Step 6: Query hooks, theme provider and toggle**

Create `frontend/src/api/queries.ts`:

```ts
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type NoteCreate, type Paper } from './client'

export const PAPERS_POLL_MS = 2000

export const queryClient = new QueryClient({
  // A local API answers or fails at once; retrying a 404 only delays the error the user needs to see.
  defaultOptions: { queries: { retry: false } },
})

const keys = {
  papers: ['papers'] as const,
  paper: (id: string) => ['papers', id] as const,
  notes: (paperId: string) => ['papers', paperId, 'notes'] as const,
}

/** Poll the library only while a paper is still ingesting. */
export function papersPollInterval(papers: Paper[] | undefined): number | false {
  return papers?.some((paper) => paper.status !== 'ready' && paper.status !== 'failed') ? PAPERS_POLL_MS : false
}

export const usePapers = () =>
  useQuery({
    queryKey: keys.papers,
    queryFn: api.listPapers,
    refetchInterval: (query) => papersPollInterval(query.state.data),
  })

export const usePaper = (id: string) => useQuery({ queryKey: keys.paper(id), queryFn: () => api.getPaper(id) })

export const useNotes = (paperId: string) =>
  useQuery({ queryKey: keys.notes(paperId), queryFn: () => api.listNotes(paperId) })

export function useUploadPapers() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadPaper(file)
    },
    onSettled: () => client.invalidateQueries({ queryKey: keys.papers }),
  })
}

export function useDeletePaper() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.deletePaper,
    onSettled: () => client.invalidateQueries({ queryKey: keys.papers }),
  })
}

export function useNoteMutations(paperId: string) {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.notes(paperId) })
  return {
    create: useMutation({ mutationFn: (note: NoteCreate) => api.createNote(note), onSuccess }),
    update: useMutation({ mutationFn: ({ id, body }: { id: string; body: string }) => api.updateNote(id, body), onSuccess }),
    remove: useMutation({ mutationFn: api.deleteNote, onSuccess }),
  }
}
```

`retry: false` matters. TanStack Query retries a failed query three times with backoff by default, so a missing paper would take about 7 s to show its error, and the reader spec's alert assertion would time out first.

Create `frontend/src/components/theme-provider.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

export type Theme = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'paperlab-theme'

type ThemeState = { theme: Theme; setTheme: (theme: Theme) => void }

const ThemeContext = createContext<ThemeState | null>(null)

// ponytail: shadcn's Vite dark-mode provider. The class is set after first paint, so a dark
// user sees one light frame on load; add an inline script in index.html if that ever bothers.
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'system')

  useEffect(() => {
    const root = document.documentElement
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = theme === 'dark' || (theme === 'system' && media.matches)
      root.classList.toggle('dark', dark)
    }
    apply()
    if (theme !== 'system') return
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  const setTheme = (next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeState {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within a ThemeProvider')
  return context
}
```

Create `frontend/src/components/mode-toggle.tsx`:

```tsx
import { Moon, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useTheme } from '@/components/theme-provider'

export function ModeToggle() {
  const { setTheme } = useTheme()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" aria-label="Toggle theme">
          <Sun className="scale-100 rotate-0 transition-all dark:scale-0 dark:-rotate-90" />
          <Moon className="absolute scale-0 rotate-90 transition-all dark:scale-100 dark:rotate-0" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme('light')}>Light</DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme('dark')}>Dark</DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme('system')}>System</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

Replace `frontend/src/main.tsx` with:

```tsx
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { queryClient } from './api/queries'
import App from './App.tsx'
import { ThemeProvider } from './components/theme-provider'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
```

- [ ] **Step 7: Move the Library page onto the components**

Replace `frontend/src/features/library/LibraryPage.tsx` with:

```tsx
import { Upload } from 'lucide-react'
import type { Paper } from '@/api/client'
import { useDeletePaper, usePapers, useUploadPapers } from '@/api/queries'
import { ModeToggle } from '@/components/mode-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import { readerHref } from '@/lib/route'

const STATUS_VARIANT = { ready: 'secondary', failed: 'destructive' } as const
const statusVariant = (status: string) => STATUS_VARIANT[status as keyof typeof STATUS_VARIANT] ?? 'outline'

export function LibraryPage() {
  const papers = usePapers()
  const upload = useUploadPapers()
  const remove = useDeletePaper()

  function onFiles(input: HTMLInputElement) {
    const files = [...(input.files ?? [])]
    input.value = ''
    if (files.length > 0) upload.mutate(files)
  }

  function onDelete(paper: Paper) {
    if (!window.confirm(`Delete "${paper.title}"? Its highlights go with it; notes are kept.`)) return
    remove.mutate(paper.id)
  }

  const error = upload.error ?? remove.error ?? papers.error
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6">
      <header className="flex items-center justify-between gap-2">
        <h1 className="font-heading text-3xl font-semibold">PaperLab</h1>
        <div className="flex items-center gap-2">
          <Button asChild>
            <label>
              <Upload aria-hidden />
              {upload.isPending ? 'Uploading…' : 'Upload PDFs'}
              <input
                type="file"
                accept="application/pdf"
                multiple
                hidden
                disabled={upload.isPending}
                onChange={(e) => onFiles(e.currentTarget)}
              />
            </label>
          </Button>
          <ModeToggle />
        </div>
      </header>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      )}

      {papers.data === undefined ? (
        papers.isError ? (
          <Button variant="outline" className="self-start" onClick={() => void papers.refetch()}>
            Retry
          </Button>
        ) : (
          <p className="text-muted-foreground">Loading…</p>
        )
      ) : papers.data.length === 0 ? (
        <p className="text-muted-foreground">No papers yet. Upload a PDF to start.</p>
      ) : (
        <Card className="py-0">
          <Table>
            <TableBody>
              {papers.data.map((paper) => (
                <TableRow key={paper.id} className="paper-row">
                  <TableCell className="whitespace-normal">
                    <a href={readerHref(paper.id)} className="font-medium hover:underline">
                      {paper.title}
                    </a>
                    {paper.status_error && <p className="text-xs text-destructive">{paper.status_error}</p>}
                  </TableCell>
                  <TableCell className="w-0">
                    <Badge variant={statusVariant(paper.status)} className="status">
                      {paper.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="w-0">
                    <Button variant="ghost" size="sm" onClick={() => onDelete(paper)}>
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </main>
  )
}
```

Replace `frontend/src/App.tsx` with this version (Task 5 replaces it):

```tsx
import { LibraryPage } from './features/library/LibraryPage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  // The reader lands in Task 5; until then a paper link shows this.
  if (route.name === 'reader')
    return (
      <p className="p-6">
        Reader coming next. <a href="#/" className="text-primary underline">Back to library</a>
      </p>
    )
  return <LibraryPage />
}
```

Delete `frontend/src/features/library/library.css`.

Run: `cd frontend && npx tsc -b && npm test && npx vite build`
Expected: no tsc output; `Tests  9 passed (9)`; `✓ built in …`.

- [ ] **Step 8: shadcn MCP server for agents**

Create `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "shadcn": {
      "command": "npx",
      "args": ["shadcn@4.21.0", "mcp", "--cwd", "frontend"]
    }
  }
}
```

`--cwd frontend` points the server at `frontend/components.json`, so "add a dialog" installs into the right project from the repo root or any worktree root. Claude Code picks it up on its next start; `/mcp` shows whether it connected.

- [ ] **Step 9: Rebuild the frontend container and run the specs**

The compose service keeps `node_modules` in an anonymous volume, and a plain rebuild reuses the old one without the new packages. `-V` recreates it:

```bash
docker compose up -d --build -V frontend
cd frontend && npm run typecheck:e2e && npx playwright test e2e/library.spec.ts e2e/theme.spec.ts
```

Expected: no type errors; `4 passed` (3 library + 1 theme).

- [ ] **Step 10: Prove the library spec still guards polling**

Polling moved from a `setInterval` into TanStack Query, so re-prove that the spec catches a library that stops polling:
1. In `frontend/src/api/queries.ts`, replace `refetchInterval: (query) => papersPollInterval(query.state.data),` with `refetchInterval: false,`.
2. Run: `cd frontend && npx playwright test -g "upload a PDF through the UI"`
   Expected: `1 failed`, with `Expected: "ready"` and `Received: "uploaded"`.
3. Undo the edit and run the same command again.
   Expected: `1 passed`.

- [ ] **Step 11: UI review**

Walk through the Library page in both themes against the "Pre-delivery check" in `frontend/design-system/MASTER.md`. Fix anything that fails and re-run Step 9. This review is extra; it doesn't replace the specs.

- [ ] **Step 12: Commit**

```bash
git add .mcp.json frontend
git status --short frontend | grep node_modules && echo "STOP: node_modules staged" || true
git commit -m "feat: shadcn/ui, Tailwind, TanStack Query and theme toggle; library page on components"
```

---

### Task 5: PDF rendering with zoom

Built on Task 4.5's components. Read `frontend/design-system/MASTER.md` first.

**Files:**
- Create: `frontend/src/features/reader/pdfjs.ts`, `usePdfDocument.ts`, `PdfPage.tsx`, `zoom.ts`, `ReaderToolbar.tsx`, `ReaderPage.tsx` (view-only version)
- Rewrite: `frontend/src/App.tsx`
- Test: `frontend/e2e/reader-render.spec.ts`

**Interfaces:**
- Consumes:
  - `api.paperFileUrl` (Task 3).
  - `usePaper`, `ModeToggle`, and the `button` and `alert` components (Task 4.5).
  - The E2E harness in `frontend/e2e/fixtures.ts` (Task 3).
- Produces:
  - `pdfjs.ts` exports `getDocument`, `TextLayerBuilder`, and types `PDFDocumentProxy`, `PDFPageProxy`. **All PDF.js imports go through this file.**
  - `usePdfDocument(url): {doc: PDFDocumentProxy | null, error: string | null}`.
  - `<PdfPage doc pageNumber scale>{overlay children}</PdfPage>` renders `div.pdf-page[data-page=N]` sized `pointSize × scale`. It contains a canvas, `div.pdf-overlay` (the children, in CSS px of the page), and the PDF.js `.textLayer`.
  - `zoom.ts`: `ZOOM_STEPS = [0.75, 1, 1.25, 1.5, 2, 2.5, 3]`, `DEFAULT_ZOOM_INDEX = 3` (150%).
  - `<ReaderToolbar title zoomIndex onZoomChange>` renders:
    - an h1 with the title
    - a "← Library" link
    - "Zoom out" and "Zoom in" icon buttons
    - `.zoom-level`, holding e.g. `150%`
    - the theme toggle
  - `<ReaderPage paperId>`. Errors show in a `role="alert"`.

- [ ] **Step 1: PDF.js entry point**

Create `frontend/src/features/reader/pdfjs.ts`:

```ts
// The single entry point to PDF.js. Import order matters: pdf_viewer.mjs reads
// globalThis.pdfjsLib, which only exists once pdfjs-dist has been evaluated.
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist'
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { TextLayerBuilder } from 'pdfjs-dist/web/pdf_viewer.mjs'
import 'pdfjs-dist/web/pdf_viewer.css'

GlobalWorkerOptions.workerSrc = workerSrc

export { getDocument, TextLayerBuilder }
export type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist'
```

PDF.js's own `pdf_viewer.css` stays: it lays out the text layer. It is unlayered, so it wins over Tailwind's reset (which lives in `@layer base`). The reset only sets `display: block` on `canvas`; `max-width: 100%` applies to images and video, so page canvases keep their size at every zoom.

- [ ] **Step 2: Document loading hook**

Create `frontend/src/features/reader/usePdfDocument.ts`:

```ts
import { useEffect, useState } from 'react'
import { getDocument, type PDFDocumentProxy } from './pdfjs'

type PdfState = { doc: PDFDocumentProxy | null; error: string | null }

export function usePdfDocument(url: string): PdfState {
  const [state, setState] = useState<PdfState>({ doc: null, error: null })

  useEffect(() => {
    let active = true
    const task = getDocument({ url })
    task.promise.then(
      (doc) => active && setState({ doc, error: null }),
      (error: Error) => active && setState({ doc: null, error: `Could not open PDF: ${error.message}` }),
    )
    return () => {
      active = false
      void task.destroy()
    }
  }, [url])

  return state
}
```

- [ ] **Step 3: Page component**

Create `frontend/src/features/reader/PdfPage.tsx`:

```tsx
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { TextLayerBuilder, type PDFDocumentProxy, type PDFPageProxy } from './pdfjs'

type Props = {
  doc: PDFDocumentProxy
  pageNumber: number
  scale: number
  /** Rendered between the canvas and the text layer, positioned in CSS pixels of this page. */
  children?: ReactNode
}

type Size = { width: number; height: number }
type RenderTask = ReturnType<PDFPageProxy['render']>

const US_LETTER: Size = { width: 612, height: 792 }

export function PdfPage({ doc, pageNumber, scale, children }: Props) {
  const pageRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const textLayerRef = useRef<HTMLDivElement>(null)
  const [pointSize, setPointSize] = useState<Size | null>(null)
  const [nearViewport, setNearViewport] = useState(false)

  // Page size is cheap to read, so every page gets its real height up front and scrolling
  // to a note on page 12 lands in the right place before pages 1-11 have rendered.
  useEffect(() => {
    let active = true
    doc.getPage(pageNumber).then((page) => {
      const { width, height } = page.getViewport({ scale: 1 })
      if (active) setPointSize({ width, height })
    }, console.error)
    return () => {
      active = false
    }
  }, [doc, pageNumber])

  // Canvases are memory-hungry; only pages within a screen of the viewport render.
  useEffect(() => {
    const page = pageRef.current!
    const observer = new IntersectionObserver(([entry]) => setNearViewport(entry.isIntersecting), {
      root: page.parentElement,
      rootMargin: '100% 0px',
    })
    observer.observe(page)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!nearViewport) return
    let active = true
    let renderTask: RenderTask | null = null
    let textLayer: TextLayerBuilder | null = null
    const canvas = canvasRef.current!

    doc
      .getPage(pageNumber)
      .then(async (page) => {
        if (!active) return
        const viewport = page.getViewport({ scale })
        const ratio = window.devicePixelRatio || 1
        canvas.width = Math.floor(viewport.width * ratio)
        canvas.height = Math.floor(viewport.height * ratio)
        renderTask = page.render({ canvas, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] })

        // TextLayerBuilder rather than bare TextLayer: it carries PDF.js's fix for
        // selections that jump across the page when the pointer crosses a gap.
        textLayer = new TextLayerBuilder({
          pdfPage: page,
          onAppend: (div: HTMLDivElement) => textLayerRef.current?.replaceChildren(div),
        })
        // The types mark `images` as required; the runtime treats it as optional.
        const textLayerOptions = { viewport } as Parameters<TextLayerBuilder['render']>[0]
        await Promise.all([renderTask.promise, textLayer.render(textLayerOptions)])
      })
      .catch((error: Error) => {
        if (active && error.name !== 'RenderingCancelledException') console.error(`page ${pageNumber}`, error)
      })

    return () => {
      active = false
      renderTask?.cancel()
      textLayer?.cancel()
      canvas.width = 0
      canvas.height = 0
    }
  }, [doc, pageNumber, scale, nearViewport])

  const size = pointSize ?? US_LETTER
  const box = { width: size.width * scale, height: size.height * scale }
  return (
    // Block layout + auto margins (not flex centering) so a page wider than the pane can still be
    // scrolled to its left edge. No border or padding: either would shift selection coordinates.
    // The page stays white in dark mode; it is the paper.
    <div
      ref={pageRef}
      className="pdf-page relative mx-auto mb-4 bg-white shadow-md"
      data-page={pageNumber}
      style={{ ...box, '--total-scale-factor': scale } as CSSProperties}
    >
      <canvas ref={canvasRef} style={box} />
      <div className="pdf-overlay pointer-events-none absolute inset-0">{children}</div>
      <div ref={textLayerRef} />
    </div>
  )
}
```

- [ ] **Step 4: Zoom steps and toolbar**

Create `frontend/src/features/reader/zoom.ts`. It's a separate file so the toolbar module exports only components, which React Fast Refresh needs:

```ts
export const ZOOM_STEPS = [0.75, 1, 1.25, 1.5, 2, 2.5, 3]
export const DEFAULT_ZOOM_INDEX = 3
```

Create `frontend/src/features/reader/ReaderToolbar.tsx`:

```tsx
import { ZoomIn, ZoomOut } from 'lucide-react'
import { ModeToggle } from '@/components/mode-toggle'
import { Button } from '@/components/ui/button'
import { ZOOM_STEPS } from './zoom'

type Props = {
  title: string | undefined
  zoomIndex: number
  onZoomChange: (index: number) => void
}

export function ReaderToolbar({ title, zoomIndex, onZoomChange }: Props) {
  return (
    <header className="col-span-full flex items-center gap-2 border-b bg-card px-4 py-2">
      <Button variant="ghost" size="sm" asChild>
        <a href="#/">← Library</a>
      </Button>
      <h1 className="mx-2 flex-1 truncate font-heading text-xl font-semibold" title={title}>
        {title ?? 'Loading…'}
      </h1>
      <Button
        variant="outline"
        size="icon"
        aria-label="Zoom out"
        disabled={zoomIndex === 0}
        onClick={() => onZoomChange(Math.max(0, zoomIndex - 1))}
      >
        <ZoomOut />
      </Button>
      <span className="zoom-level min-w-14 text-center text-sm tabular-nums">
        {Math.round(ZOOM_STEPS[zoomIndex] * 100)}%
      </span>
      <Button
        variant="outline"
        size="icon"
        aria-label="Zoom in"
        disabled={zoomIndex === ZOOM_STEPS.length - 1}
        onClick={() => onZoomChange(Math.min(ZOOM_STEPS.length - 1, zoomIndex + 1))}
      >
        <ZoomIn />
      </Button>
      <ModeToggle />
    </header>
  )
}
```

- [ ] **Step 5: View-only reader page**

Create `frontend/src/features/reader/ReaderPage.tsx` (Task 6 replaces it with the note-taking version):

```tsx
import { useState } from 'react'
import { api } from '@/api/client'
import { usePaper } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { PdfPage } from './PdfPage'
import { ReaderToolbar } from './ReaderToolbar'
import { usePdfDocument } from './usePdfDocument'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from './zoom'

export function ReaderPage({ paperId }: { paperId: string }) {
  const { doc, error: pdfError } = usePdfDocument(api.paperFileUrl(paperId))
  const paper = usePaper(paperId)
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const scale = ZOOM_STEPS[zoomIndex]

  const shownError = paper.error?.message ?? pdfError
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)_360px] grid-rows-[auto_minmax(0,1fr)]">
      <ReaderToolbar title={paper.data?.title} zoomIndex={zoomIndex} onZoomChange={setZoomIndex} />

      {shownError && (
        <Alert variant="destructive" className="fixed bottom-4 left-4 z-10 w-auto max-w-md shadow-lg">
          <AlertDescription>{shownError}</AlertDescription>
        </Alert>
      )}

      <section className="overflow-auto bg-muted p-4">
        {doc &&
          Array.from({ length: doc.numPages }, (_, i) => i + 1).map((pageNumber) => (
            <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} scale={scale} />
          ))}
      </section>

      {/* Notes panel column; filled in by Task 6. */}
      <aside className="border-l" />
    </div>
  )
}
```

- [ ] **Step 6: Route to the reader**

Replace `frontend/src/App.tsx` with the final version:

```tsx
import { LibraryPage } from './features/library/LibraryPage'
import { ReaderPage } from './features/reader/ReaderPage'
import { useRoute } from './lib/route'

export default function App() {
  const route = useRoute()
  return route.name === 'reader' ? <ReaderPage key={route.paperId} paperId={route.paperId} /> : <LibraryPage />
}
```

- [ ] **Step 7: Reader rendering E2E spec**

This spec checks the reader against the backend's own data:
- The canvas actually has ink on it.
- The PDF.js text layer sits inside the rect PyMuPDF stored for the same text, at three zoom levels. This is also what proves Tailwind's reset doesn't move the text layer.
- Pages scale with zoom.
- A missing paper shows an error instead of a blank screen.

Create `frontend/e2e/reader-render.spec.ts`:

```ts
import { FIXTURE_TITLE, expect, openReader, test, type Rect } from './fixtures'

const LETTER_WIDTH_PT = 612

test('renders every page with ink, and the text layer sits on PyMuPDF’s chunk at each zoom', async ({
  page,
  request,
  paperId,
}) => {
  const line = await openReader(page, paperId)
  await expect(page.getByRole('heading', { name: FIXTURE_TITLE })).toBeVisible()
  await expect(page.locator('.pdf-page')).toHaveCount(2)

  const firstPage = page.locator('.pdf-page[data-page="1"]')
  // A correctly sized but blank canvas would pass every other check, so count dark pixels.
  await expect
    .poll(() =>
      firstPage.locator('canvas').evaluate((canvas: HTMLCanvasElement) => {
        const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height)
        let dark = 0
        for (let i = 0; i < data.length; i += 4) if (data[i] < 128) dark++
        return dark
      }),
    )
    .toBeGreaterThan(100)

  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const [x0, y0, x1, y1] = chunk.bbox[0] as Rect
  const tolerance = 4

  for (const [zoomLabel, scale] of [['150%', 1.5], ['200%', 2], ['125%', 1.25]] as const) {
    if (zoomLabel === '200%') await page.getByRole('button', { name: 'Zoom in' }).click()
    if (zoomLabel === '125%') {
      await page.getByRole('button', { name: 'Zoom out' }).click()
      await page.getByRole('button', { name: 'Zoom out' }).click()
    }
    await expect(page.locator('.zoom-level')).toHaveText(zoomLabel)
    await expect.poll(async () => (await firstPage.boundingBox())?.width).toBeCloseTo(LETTER_WIDTH_PT * scale, 0)

    await expect
      .poll(async () => {
        const pageBox = (await firstPage.boundingBox())!
        const lineBox = await line.boundingBox()
        if (!lineBox) return false
        return (
          lineBox.x >= pageBox.x + x0 * scale - tolerance &&
          lineBox.y >= pageBox.y + y0 * scale - tolerance &&
          lineBox.x + lineBox.width <= pageBox.x + x1 * scale + tolerance &&
          lineBox.y + lineBox.height <= pageBox.y + y1 * scale + tolerance
        )
      })
      .toBe(true)
  }

  await page.getByRole('link', { name: '← Library' }).click()
  await expect(page.getByRole('heading', { name: 'PaperLab' })).toBeVisible()
})

test('a missing paper shows an error instead of a blank reader', async ({ page }) => {
  await page.goto('/#/papers/00000000-0000-0000-0000-000000000000')
  await expect(page.getByRole('alert')).toBeVisible()
})
```

Run: `cd frontend && npm run typecheck:e2e && npm run e2e`
Expected: no type errors; `6 passed` (3 library + 1 theme + 2 reader).

- [ ] **Step 8: Prove the reader spec catches rendering bugs**

Each break below must turn `npx playwright test -g "renders every page"` red. Undo each one before starting the next.
1. **No text layer.** In `PdfPage.tsx`, replace `await Promise.all([renderTask.promise, textLayer.render(textLayerOptions)])` with `await renderTask.promise`.
   Expected: `1 failed`.
2. **Blank canvas.** In `PdfPage.tsx`, replace `renderTask = page.render(` with `renderTask = page.render.bind(page, `. The page is now never drawn.
   Expected: `1 failed`.

After undoing both, run the same command again. Expected: `1 passed`.

- [ ] **Step 9: Verify**

Run: `cd frontend && npx tsc -b && npm test && npx vite build`
Expected:
- No tsc output.
- `Tests  9 passed (9)`.
- Vite prints `✓ built in …`. A ">500 kB chunk" warning from pdfjs is expected (roadmap K5).

Manual check at http://localhost:5180, in addition to the automated tests. Open a `ready` two-column paper and check, in light and dark theme:
- Pages render sharply and stay white in dark mode.
- The browser console shows no errors.
- Text can be selected with the mouse, and the selection follows the words.
- Scrolling a long paper renders pages as they approach.
- The toolbar passes the "Pre-delivery check" in `frontend/design-system/MASTER.md`.

- [ ] **Step 10: Commit**

```bash
git add frontend/src frontend/e2e
git commit -m "feat: PDF.js reader with text layer, zoom, and lazy page rendering"
```

---

### Task 6: Highlight → note (E2E first)

Built on Task 4.5's components. Read `frontend/design-system/MASTER.md` first.

**Files:**
- Test: `frontend/e2e/highlight-to-note.spec.ts`. The Playwright config, fixture paper and `fixtures.ts` already exist from Task 3.
- Create: `frontend/src/features/reader/selection.ts`
- Create: `frontend/src/features/notes/ProvenanceBadge.tsx`, `NoteComposer.tsx`, `NoteCard.tsx`, `NotesPanel.tsx`
- Rewrite: `frontend/src/features/reader/ReaderPage.tsx`

**Interfaces:**
- Consumes:
  - `useNotes`, `useNoteMutations`, `usePaper` (Task 4.5) and the `Note` type (Task 3).
  - The `badge`, `button`, `card`, `textarea` and `alert` components, the `provenance-llm*` and `highlight*` tokens, and `cn` (Task 4.5).
  - `pdfRectToCss`, `clientRectsToPdfRects`, `PdfRect` (Task 4).
  - `PdfPage` with overlay children, rendering `.pdf-page[data-page]`; `ReaderToolbar`; `ZOOM_STEPS`, `DEFAULT_ZOOM_INDEX` (Task 5).
  - From `frontend/e2e/fixtures.ts` (Task 3): `test` with `paperId`, `openReader`, `selectText`, `saveNoteOn`, `boxOffset`.
- Produces:
  - `readSelection(scale): SelectionResult` (`{kind:'none'} | {kind:'invalid', reason} | {kind:'anchor', anchor: SelectionAnchor}`), where `SelectionAnchor = {page, rects: PdfRect[], quotedText}`.
  - DOM contract the E2E relies on:
    - `.highlight[data-note-id]` (saved) and `.highlight.draft` (pending selection) inside `.pdf-overlay`.
    - Saved notes are `article.note` cards containing `.provenance-badge` ("You", "AI", "AI · edited"). The draft composer is a `form`, never an `article`.
    - A textbox labelled `Note` and a button `Save note`; on each card, `Edit`, `Save`, `Delete` and a textbox labelled `Edit note`.

- [ ] **Step 1: Write the failing E2E spec**

Five behaviours, each its own test. Every test gets a fresh paper from the `paperId` fixture:
- Create a note, then reload: the highlight is still on the text, and the stored anchor lies inside PyMuPDF's chunk.
- Highlights follow zoom.
- Editing a human note keeps the "You" badge.
- Deleting a note removes its card and its highlight.
- A selection across two pages is rejected.

Create `frontend/e2e/highlight-to-note.spec.ts`:

```ts
import { boxOffset, expect, openReader, saveNoteOn, selectText, test, type Rect } from './fixtures'

test('select a passage, save a note, and find it highlighted after reload', async ({ page, request, paperId }) => {
  const line = await openReader(page, paperId)
  const card = await saveNoteOn(page, line, 'The anchor is the whole point.')
  await expect(card).toContainText('Highlights are the anchor')
  await expect(card.locator('.provenance-badge')).toHaveText('You')

  // The stored anchor (PDF.js coordinates) must sit inside the chunk PyMuPDF extracted.
  const [note] = await (await request.get(`/api/papers/${paperId}/notes`)).json()
  const [chunk] = await (await request.get(`/api/papers/${paperId}/chunks?page=1`)).json()
  const [nx0, ny0, nx1, ny1] = note.anchors[0].bbox[0] as Rect
  const [cx0, cy0, cx1, cy1] = chunk.bbox[0] as Rect
  const tolerance = 3
  expect(nx0).toBeGreaterThanOrEqual(cx0 - tolerance)
  expect(ny0).toBeGreaterThanOrEqual(cy0 - tolerance)
  expect(nx1).toBeLessThanOrEqual(cx1 + tolerance)
  expect(ny1).toBeLessThanOrEqual(cy1 + tolerance)
  expect(note.anchors[0].quoted_text).toContain('Highlights are the anchor')

  // After a reload, the highlight is drawn from stored PDF points over the same text.
  await page.reload()
  await expect(page.locator('article.note', { hasText: 'The anchor is the whole point.' })).toBeVisible()
  const highlight = page.locator(`.highlight[data-note-id="${note.id}"]`).first()
  await expect.poll(() => boxOffset(line, highlight)).toBeLessThan(4)
})

test('highlights stay on their text when zooming', async ({ page, paperId }) => {
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'zoom check')
  const highlight = page.locator('.highlight:not(.draft)').first()

  for (const button of ['Zoom in', 'Zoom out', 'Zoom out']) {
    await page.getByRole('button', { name: button }).click()
    await expect.poll(() => boxOffset(line, highlight)).toBeLessThan(4)
  }
})

test('editing a human note keeps the "You" badge and survives reload', async ({ page, paperId }) => {
  const line = await openReader(page, paperId)
  await saveNoteOn(page, line, 'first draft')
  const card = page.locator('article.note', { hasText: 'Highlights are the anchor' })

  await card.getByRole('button', { name: 'Edit' }).click()
  await card.getByRole('textbox', { name: 'Edit note' }).fill('second thought')
  await card.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(card).toContainText('second thought')
  await expect(card.locator('.provenance-badge')).toHaveText('You')
  await page.reload()
  await expect(page.locator('article.note', { hasText: 'Highlights are the anchor' })).toContainText('second thought')
})

test('deleting a note removes its card and its highlight', async ({ page, request, paperId }) => {
  const line = await openReader(page, paperId)
  const card = await saveNoteOn(page, line, 'to be deleted')
  await expect(page.locator('.highlight')).not.toHaveCount(0)

  page.once('dialog', (dialog) => dialog.accept())
  await card.getByRole('button', { name: 'Delete' }).click()

  await expect(card).toHaveCount(0)
  await expect(page.locator('.highlight')).toHaveCount(0)
  expect(await (await request.get(`/api/papers/${paperId}/notes`)).json()).toEqual([])
})

test('a selection spanning two pages is rejected with a message', async ({ page, paperId }) => {
  const firstPageLine = await openReader(page, paperId)
  const secondPageLine = page.locator('.pdf-page[data-page="2"] .textLayer span', { hasText: 'The second page' })
  await secondPageLine.scrollIntoViewIfNeeded()
  await expect(secondPageLine).toBeVisible()

  await selectText(firstPageLine, secondPageLine)

  await expect(page.getByRole('alert')).toContainText('Select text within a single page')
  await expect(page.getByRole('textbox', { name: 'Note' })).toHaveCount(0)
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm run typecheck:e2e && npx playwright test e2e/highlight-to-note.spec.ts`
Expected: no type errors, then `5 failed`:
- Four with `TimeoutError: locator.fill: Timeout 10000ms exceeded`, waiting for the `Note` textbox (no composer exists yet).
- The cross-page test on `expect(locator).toContainText` (no alert).

The `paperId` fixture still deletes every uploaded paper, so the library's paper count is unchanged.

- [ ] **Step 3: Selection capture**

Create `frontend/src/features/reader/selection.ts`:

```ts
import { clientRectsToPdfRects, type PdfRect } from './coords'

export type SelectionAnchor = { page: number; rects: PdfRect[]; quotedText: string }

export type SelectionResult =
  | { kind: 'none' }
  | { kind: 'invalid'; reason: string }
  | { kind: 'anchor'; anchor: SelectionAnchor }

const pageElementOf = (node: Node) =>
  (node instanceof Element ? node : node.parentElement)?.closest<HTMLElement>('.pdf-page') ?? null

/** Reads the browser selection as an anchor in PDF points on a single page. */
export function readSelection(scale: number): SelectionResult {
  const selection = window.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return { kind: 'none' }

  const range = selection.getRangeAt(0)
  const page = pageElementOf(range.startContainer)
  if (!page) return { kind: 'none' }
  if (page !== pageElementOf(range.endContainer)) {
    return { kind: 'invalid', reason: 'Select text within a single page to make a note.' }
  }

  const quotedText = selection.toString().trim()
  const rects = clientRectsToPdfRects([...range.getClientRects()], page.getBoundingClientRect(), scale)
  if (!quotedText || rects.length === 0) return { kind: 'none' }
  return { kind: 'anchor', anchor: { page: Number(page.dataset.page), rects, quotedText } }
}
```

- [ ] **Step 4: Provenance badge**

Create `frontend/src/features/notes/ProvenanceBadge.tsx`:

```tsx
import { Sparkles, UserRound } from 'lucide-react'
import type { Note } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type Provenance = Note['provenance']

const LABEL: Record<Provenance, string> = {
  human: 'You',
  llm: 'AI',
  llm_edited: 'AI · edited',
}

const DESCRIPTION: Record<Provenance, string> = {
  human: 'Written by you',
  llm: 'Generated by a model. Verify before citing.',
  llm_edited: 'Generated by a model, then edited by you. Verify before citing.',
}

export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  const human = provenance === 'human'
  return (
    // An icon as well as a colour, so provenance never depends on colour vision.
    <Badge
      variant={human ? 'secondary' : 'default'}
      className={cn('provenance-badge', !human && 'bg-provenance-llm text-provenance-llm-foreground')}
      title={DESCRIPTION[provenance]}
    >
      {human ? <UserRound aria-hidden /> : <Sparkles aria-hidden />}
      {LABEL[provenance]}
    </Badge>
  )
}
```

- [ ] **Step 5: Composer, card, and panel**

Create `frontend/src/features/notes/NoteComposer.tsx`:

```tsx
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import type { SelectionAnchor } from '../reader/selection'

type Props = {
  draft: SelectionAnchor
  onSave: (body: string) => Promise<boolean>
  onCancel: () => void
}

export function NoteComposer({ draft, onSave, onCancel }: Props) {
  const [body, setBody] = useState('')
  const [saving, setSaving] = useState(false)

  async function save() {
    setSaving(true)
    await onSave(body)
    setSaving(false)
  }

  return (
    // A form, not an <article>: saved notes are the only articles in the panel.
    <form
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <Card size="sm" className="ring-2 ring-primary">
        <CardContent className="flex flex-col gap-2">
          <blockquote className="border-l-2 pl-2 text-muted-foreground">{draft.quotedText}</blockquote>
          <Textarea
            autoFocus
            aria-label="Note"
            placeholder="Your note (optional). Ctrl/⌘+Enter saves."
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                void save()
              }
              if (e.key === 'Escape') onCancel()
            }}
          />
        </CardContent>
        <CardFooter className="justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            Save note
          </Button>
        </CardFooter>
      </Card>
    </form>
  )
}
```

Create `frontend/src/features/notes/NoteCard.tsx`:

```tsx
import { useState } from 'react'
import type { Note } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { ProvenanceBadge } from './ProvenanceBadge'

type Props = {
  note: Note
  paperId: string
  active: boolean
  onSelect: () => void
  onUpdate: (body: string) => Promise<boolean>
  onDelete: () => Promise<void>
}

export function NoteCard({ note, paperId, active, onSelect, onUpdate, onDelete }: Props) {
  const [editing, setEditing] = useState(false)
  const [body, setBody] = useState(note.body)
  const anchor = note.anchors.find((a) => a.paper_id === paperId)

  async function save() {
    if (await onUpdate(body)) setEditing(false)
  }

  function cancel() {
    setBody(note.body)
    setEditing(false)
  }

  return (
    <article className="note" data-note-id={note.id}>
      {/* Provenance is never subtle: every note shows a badge, and AI text gets its own background. */}
      <Card
        size="sm"
        className={cn(note.provenance !== 'human' && 'bg-provenance-llm-surface', active && 'ring-2 ring-primary')}
      >
        <CardHeader className="flex items-center justify-between">
          <ProvenanceBadge provenance={note.provenance} />
          {anchor && (
            <Button variant="link" size="xs" onClick={onSelect}>
              p. {anchor.page}
            </Button>
          )}
        </CardHeader>

        <CardContent className="flex flex-col gap-2">
          {anchor && (
            <blockquote className="cursor-pointer border-l-2 pl-2 text-muted-foreground" onClick={onSelect}>
              {anchor.quoted_text}
            </blockquote>
          )}
          {editing ? (
            <Textarea autoFocus aria-label="Edit note" value={body} onChange={(e) => setBody(e.target.value)} />
          ) : (
            note.body && <p className="whitespace-pre-wrap">{note.body}</p>
          )}
        </CardContent>

        <CardFooter className="justify-end gap-2">
          {editing ? (
            <>
              <Button variant="ghost" size="sm" onClick={cancel}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => void save()}>
                Save
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
              <Button variant="ghost" size="sm" className="text-destructive" onClick={() => void onDelete()}>
                Delete
              </Button>
            </>
          )}
        </CardFooter>
      </Card>
    </article>
  )
}
```

Create `frontend/src/features/notes/NotesPanel.tsx`:

```tsx
import type { Note } from '@/api/client'
import type { SelectionAnchor } from '../reader/selection'
import { NoteCard } from './NoteCard'
import { NoteComposer } from './NoteComposer'

type Props = {
  paperId: string
  notes: Note[]
  draft: SelectionAnchor | null
  activeNoteId: string | null
  onSaveDraft: (body: string) => Promise<boolean>
  onCancelDraft: () => void
  onSelectNote: (note: Note) => void
  onUpdateNote: (note: Note, body: string) => Promise<boolean>
  onDeleteNote: (note: Note) => Promise<void>
}

// A new selection must reset the composer's text, so the draft's position is its identity.
const draftKey = (draft: SelectionAnchor) => `${draft.page}:${draft.rects.flat().join(',')}`

export function NotesPanel(props: Props) {
  const { paperId, notes, draft, activeNoteId } = props
  return (
    <aside className="flex flex-col gap-3 overflow-auto border-l bg-background p-4" aria-label="Notes">
      {draft ? (
        <NoteComposer key={draftKey(draft)} draft={draft} onSave={props.onSaveDraft} onCancel={props.onCancelDraft} />
      ) : (
        <p className="text-sm text-muted-foreground">Select text in the paper to add a note.</p>
      )}
      {notes.map((note) => (
        <NoteCard
          key={note.id}
          note={note}
          paperId={paperId}
          active={note.id === activeNoteId}
          onSelect={() => props.onSelectNote(note)}
          onUpdate={(body) => props.onUpdateNote(note, body)}
          onDelete={() => props.onDeleteNote(note)}
        />
      ))}
    </aside>
  )
}
```

- [ ] **Step 6: Wire notes into the reader**

Replace `frontend/src/features/reader/ReaderPage.tsx` with:

```tsx
import { useMemo, useState } from 'react'
import { api, type Note } from '@/api/client'
import { useNoteMutations, useNotes, usePaper } from '@/api/queries'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { NotesPanel } from '../notes/NotesPanel'
import { pdfRectToCss, type PdfRect } from './coords'
import { PdfPage } from './PdfPage'
import { ReaderToolbar } from './ReaderToolbar'
import { readSelection, type SelectionAnchor } from './selection'
import { usePdfDocument } from './usePdfDocument'
import { DEFAULT_ZOOM_INDEX, ZOOM_STEPS } from './zoom'

type PageHighlight = { key: string; noteId: string | null; rect: PdfRect }

function groupHighlights(notes: Note[], draft: SelectionAnchor | null, paperId: string) {
  const byPage = new Map<number, PageHighlight[]>()
  const add = (page: number, highlight: PageHighlight) =>
    byPage.set(page, [...(byPage.get(page) ?? []), highlight])

  for (const note of notes) {
    note.anchors.forEach((anchor, a) => {
      if (anchor.paper_id !== paperId) return
      anchor.bbox.forEach((rect, r) => add(anchor.page, { key: `${note.id}-${a}-${r}`, noteId: note.id, rect }))
    })
  }
  draft?.rects.forEach((rect, r) => add(draft.page, { key: `draft-${r}`, noteId: null, rect }))
  return byPage
}

export function ReaderPage({ paperId }: { paperId: string }) {
  const { doc, error: pdfError } = usePdfDocument(api.paperFileUrl(paperId))
  const paper = usePaper(paperId)
  const notesQuery = useNotes(paperId)
  const mutations = useNoteMutations(paperId)
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const [draft, setDraft] = useState<SelectionAnchor | null>(null)
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const scale = ZOOM_STEPS[zoomIndex]
  const notes = useMemo(() => notesQuery.data ?? [], [notesQuery.data])

  const highlightsByPage = useMemo(() => groupHighlights(notes, draft, paperId), [notes, draft, paperId])

  /** Runs a mutation; failures show in the alert instead of throwing. */
  async function attempt(action: () => Promise<unknown>): Promise<boolean> {
    try {
      await action()
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return false
    }
  }

  function captureSelection() {
    const result = readSelection(scale)
    if (result.kind === 'invalid') setError(result.reason)
    if (result.kind === 'anchor') {
      setError(null)
      setDraft(result.anchor)
    }
  }

  async function saveDraft(body: string): Promise<boolean> {
    if (!draft) return false
    const anchor = { paper_id: paperId, page: draft.page, bbox: draft.rects, quoted_text: draft.quotedText }
    const saved = await attempt(() => mutations.create.mutateAsync({ body, anchor }))
    if (saved) {
      setDraft(null)
      window.getSelection()?.removeAllRanges()
    }
    return saved
  }

  async function deleteNote(note: Note) {
    if (!window.confirm('Delete this note?')) return
    await attempt(() => mutations.remove.mutateAsync(note.id))
  }

  function focusNote(note: Note) {
    setActiveNoteId(note.id)
    document
      .querySelector(`.highlight[data-note-id="${note.id}"]`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const shownError = error ?? paper.error?.message ?? notesQuery.error?.message ?? pdfError
  return (
    <div className="grid h-dvh grid-cols-[minmax(0,1fr)_360px] grid-rows-[auto_minmax(0,1fr)]">
      <ReaderToolbar title={paper.data?.title} zoomIndex={zoomIndex} onZoomChange={setZoomIndex} />

      {shownError && (
        <Alert
          variant="destructive"
          className="fixed bottom-4 left-4 z-10 w-auto max-w-md cursor-pointer shadow-lg"
          onClick={() => setError(null)}
        >
          <AlertDescription>{shownError}</AlertDescription>
        </Alert>
      )}

      <section className="overflow-auto bg-muted p-4" onMouseUp={captureSelection}>
        {doc &&
          Array.from({ length: doc.numPages }, (_, i) => i + 1).map((pageNumber) => (
            <PdfPage key={pageNumber} doc={doc} pageNumber={pageNumber} scale={scale}>
              {(highlightsByPage.get(pageNumber) ?? []).map((h) => (
                <div
                  key={h.key}
                  data-note-id={h.noteId ?? undefined}
                  className={cn(
                    'highlight absolute rounded-xs bg-highlight mix-blend-multiply',
                    h.noteId === null && 'draft bg-highlight-draft',
                    h.noteId !== null && h.noteId === activeNoteId && 'active bg-highlight-active',
                  )}
                  style={pdfRectToCss(h.rect, scale)}
                />
              ))}
            </PdfPage>
          ))}
      </section>

      <NotesPanel
        paperId={paperId}
        notes={notes}
        draft={draft}
        activeNoteId={activeNoteId}
        onSaveDraft={saveDraft}
        onCancelDraft={() => setDraft(null)}
        onSelectNote={focusNote}
        onUpdateNote={(note, body) => attempt(() => mutations.update.mutateAsync({ id: note.id, body }))}
        onDeleteNote={deleteNote}
      />
    </div>
  )
}
```

- [ ] **Step 7: Run everything**

Run: `cd frontend && npx tsc -b && npm test && npm run typecheck:e2e && npm run e2e`
Expected:
- No tsc output.
- `Tests  9 passed (9)`.
- No e2e type errors.
- `11 passed` (3 library + 1 theme + 2 reader + 5 highlight-to-note).

If a spec fails, use superpowers:systematic-debugging. Start by opening the trace printed in the failure (`npx playwright show-trace …`) and checking the browser console for `pageerror`s before changing code.

- [ ] **Step 8: Prove the note specs guard the rules that matter**

Each break below must turn the named test red. Undo each one before the next.

| Break | File and change | Run | Expected |
|---|---|---|---|
| Highlights ignore zoom | `coords.ts`: `top: y0 * scale,` → `top: y0 * 1.5,` | `npx playwright test -g "highlights stay on their text"` | `1 failed` |
| Cross-page selection allowed | `selection.ts`: `if (page !== pageElementOf(range.endContainer)) {` → `if (false) {` | `npx playwright test -g "spanning two pages"` | `1 failed` |
| Human note mislabelled as AI | `ProvenanceBadge.tsx`: `human: 'You',` → `human: 'AI',` | `npx playwright test -g "save a note"` | `1 failed` |
| Edits never saved | `NoteCard.tsx`: `if (await onUpdate(body)) setEditing(false)` → `setEditing(false)` | `npx playwright test -g "editing a human note"` | `1 failed` |

After undoing all four, `npm run e2e` must show `11 passed` again.

- [ ] **Step 9: UI review**

In light and dark theme, create, edit and delete a note, and tab through the notes panel. Check it against the "Pre-delivery check" in `frontend/design-system/MASTER.md`. Every fix re-runs Step 7.

- [ ] **Step 10: Commit**

```bash
git add frontend
git commit -m "feat: highlight passages into notes with provenance badges"
```

---

### Task 7: "Does it feel good" checkpoint, verification, finish

The brief makes this a hard gate: "If this doesn't feel good to use, stop and fix it before building on top."

**Files:**
- Modify: `docs/superpowers/plans/2026-09-13-paperlab-roadmap.md`

**Interfaces:**
- Consumes: the whole M3 feature.
- Produces: M3 marked done on the roadmap board; branch merged per the owner's choice.

- [ ] **Step 1: Human walkthrough (the owner does this; agents stop and ask)**

Use at least one of your own two-column papers with figures, at http://localhost:5180:
- [ ] Dragging across a paragraph selects the words under the pointer, without jumping to the end of the page.
- [ ] Highlights sit on the text at 75%, 150%, and 300%.
- [ ] Ctrl/⌘+Enter saves a note; Escape cancels the draft.
- [ ] Clicking a note's quote or page number scrolls to its highlight, including notes on later pages.
- [ ] Editing and deleting a note work; a reload keeps everything.
- [ ] Selecting across two pages shows "Select text within a single page…".
- [ ] A scanned PDF shows its failure reason in the library.
- [ ] Light, Dark and System themes all read comfortably; the PDF page stays white; AI and human notes are told apart by badge icon and label, not colour alone.
- [ ] The "Pre-delivery check" in `frontend/design-system/MASTER.md` passes on the library, reader and notes panel, in both themes, using only the keyboard to reach every control.

Anything that feels wrong gets fixed in this branch before continuing, using superpowers:systematic-debugging. **Every fix lands with a test that fails without it:** a Vitest test when the fix is logic, or a new test in the matching E2E spec when it is a flow. Re-run the whole suite after each fix.

- [ ] **Step 2: Bring in main's test pack and run the full exit criteria**

`main` carries the M1–M2 test pack and the 80% coverage gate (roadmap D21). Merge it so M3 is held to the same bar. Run this in the worktree, and resolve any conflict by keeping the tests from both sides:

```bash
git merge main
```

Then use superpowers:verification-before-completion and read the output of each command:

```bash
cd backend && uv run pytest --cov && uv run ruff check . && (grep -r fastapi app/core/ || echo "core clean")
cd ../frontend && npx tsc -b && npm test && npm run typecheck:e2e && npm run e2e
```

Expected:
- **pytest:** every test passes, including `tests/test_invariants.py` (no fastapi in core; migrations round-trip) and `tests/test_notes_edges.py`, and the gate prints `Required test coverage of 80% reached`. At plan time this was 47 tests at 97.5%.
- **Ruff and core check:** `All checks passed!`, `core clean`.
- **Frontend:** `Tests  9 passed (9)`, no e2e type errors, `11 passed`.

A count lower than these means a test was skipped or deleted. Find out why before continuing.

- [ ] **Step 3: Code review**

Use superpowers:requesting-code-review on the `m3-reader-notes` branch diff against `main`. Fix Critical/Important findings and re-run Step 2.

- [ ] **Step 4: Update the roadmap**

In `docs/superpowers/plans/2026-09-13-paperlab-roadmap.md`:
- Set M1 and M2 status to `✅ Done`.
- Set M3 to `✅ Done`, with the date.
- Set M4 to `⏭ Next`.
- Add decision-log entries for anything decided during the walkthrough or review.
- Add any new known issues.

```bash
git add docs/superpowers/plans/2026-09-13-paperlab-roadmap.md
git commit -m "docs: mark M3 done on the roadmap"
```

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch. After merging, run `docker compose up -d --build` from the main checkout so the stack serves `main` again.
