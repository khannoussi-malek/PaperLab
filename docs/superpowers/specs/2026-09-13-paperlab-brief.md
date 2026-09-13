# PaperLab — project brief

Use this as the initial prompt for a coding agent, or as your own reference while
scaffolding. It describes what to build, what to build it with, and — as important —
what to leave out.

> **Amended by [addendum 1](2026-09-13-paperlab-brief-addendum-1.md)** (global questions, references, topics,
> authors, community detection, revised build order from step 6.5). Where they conflict, the addendum wins.

---

## What the app is

A local-first research reading tool. You load PDFs of academic papers. The app
extracts them, lets you read them in-browser, highlight passages and turn those into
notes, ask questions that get answered from the papers with citations that jump back
to the exact spot on the page, organise everything into categories, and see a graph
of how papers and notes connect.

The same library is exposed over MCP, so Claude Desktop (or any MCP client) can
search it and write notes into it.

Single user. Runs on one machine. No auth, no multi-tenancy, no cloud deployment.

**The design centre:** the note is the primary object, not the paper. A paper page is
"notes anchored here". A category is "notes tagged this". The graph is "notes and
what they connect". Build the schema that way.

**The non-negotiable rule:** every piece of LLM-generated text is stored separately
from what the human wrote, and is visibly marked in the UI. A researcher who can't
tell later whether a claim came from them or from a model has notes they can't cite.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI | PDF and ML ecosystem lives here |
| ORM | SQLAlchemy 2.0 async | only mature option with pgvector support |
| Migrations | Alembic | |
| DB | Postgres 16 + pgvector | vectors, full-text, relational, graph — one system |
| Queue | ARQ + Redis | async-native, a tenth of Celery's config |
| PDF | PyMuPDF | text with bounding boxes, natively |
| Embeddings | sentence-transformers, `nomic-embed-text-v1.5` (768d) | in-process, CPU, free |
| Rerank | `bge-reranker-v2-m3` cross-encoder | biggest single win in answer quality |
| Generation | Ollama on host (`qwen2.5:7b-instruct`), Anthropic API optional | swappable behind one interface |
| Frontend | React + TypeScript + Vite | |
| PDF viewer | PDF.js | |
| Graph | react-force-graph | |
| MCP | official Python SDK (`FastMCP`) | imports the core directly |

---

## Repo layout

```
paperlab/
  docker-compose.yml
  .env.example
  backend/
    pyproject.toml
    Dockerfile
    alembic/
    prompts/
      summarize_section.v1.md
      explain_passage.v1.md
      compare_papers.v1.md
    app/
      main.py            app factory, router mounting, exception handlers
      config.py          pydantic-settings
      db.py              async engine, async_sessionmaker, session dependency
      api/               thin routers: papers, notes, categories, chat, graph, models
      core/              domain services — NO fastapi imports in this package
        papers.py
        chunking.py      pure functions, no I/O
        retrieval.py
        notes.py
        graph.py
        enrichment.py    OpenAlex client
        errors.py        domain exceptions
      models/            SQLAlchemy tables
      schemas/           Pydantic request/response
      providers/
        base.py          Protocol definitions
        embeddings.py
        llm.py           ollama + anthropic adapters
        extraction.py    PyMuPDF wrapper
      workers/
        settings.py
        ingest.py
    evals/
      questions.yaml     20 questions with expected chunk IDs
      run.py             prints recall@k
  mcp_server/
    server.py            imports backend.app.core
  frontend/
    src/
      api/               generated OpenAPI types + fetch wrappers
      features/
        reader/          PDF.js viewer, highlight overlay, selection capture
        notes/
        chat/
        graph/
        settings/        model manager
      components/
```

**Enforced invariant:** `grep -r "fastapi" backend/app/core/` returns nothing. Services
take plain arguments and an injected session, return domain objects or dicts, and raise
domain exceptions. The API layer has one handler mapping those to status codes. This is
what lets the MCP server call the same services without duplicating logic.

---

## Database schema

```sql
CREATE EXTENSION vector;

CREATE TABLE papers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  doi           text UNIQUE,
  openalex_id   text UNIQUE,
  title         text NOT NULL,
  abstract      text,
  authors       jsonb DEFAULT '[]',
  year          int,
  venue         text,
  file_path     text NOT NULL,
  page_count    int,
  status        text NOT NULL DEFAULT 'uploaded',
  status_error  text,
  created_at    timestamptz DEFAULT now()
);

CREATE TABLE chunks (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id       uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  ordinal        int NOT NULL,
  page           int NOT NULL,
  bbox           jsonb NOT NULL,
  section_title  text,
  text           text NOT NULL,
  tsv            tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding      vector(768),
  embed_model    text NOT NULL,
  strategy_ver   int NOT NULL,
  UNIQUE (paper_id, ordinal)
);

CREATE TABLE categories (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id  uuid REFERENCES categories(id) ON DELETE CASCADE,
  name       text NOT NULL,
  UNIQUE (parent_id, name)
);

CREATE TABLE llm_outputs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  paper_id       uuid REFERENCES papers(id) ON DELETE CASCADE,
  kind           text NOT NULL,
  content        text NOT NULL,
  cited_chunks   uuid[] DEFAULT '{}',
  model          text NOT NULL,
  prompt_version int NOT NULL,
  created_at     timestamptz DEFAULT now()
);

CREATE TABLE notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  body        text NOT NULL,
  provenance  text NOT NULL CHECK (provenance IN ('human','llm','llm_edited')),
  source_id   uuid REFERENCES llm_outputs(id),
  embedding   vector(768),
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

CREATE TABLE note_anchors (
  note_id      uuid REFERENCES notes(id) ON DELETE CASCADE,
  paper_id     uuid NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  chunk_id     uuid REFERENCES chunks(id) ON DELETE SET NULL,
  page         int,
  bbox         jsonb,
  quoted_text  text,
  PRIMARY KEY (note_id, paper_id, page, bbox)
);

CREATE TABLE note_categories (
  note_id     uuid REFERENCES notes(id) ON DELETE CASCADE,
  category_id uuid REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (note_id, category_id)
);

CREATE TABLE paper_categories (
  paper_id    uuid REFERENCES papers(id) ON DELETE CASCADE,
  category_id uuid REFERENCES categories(id) ON DELETE CASCADE,
  PRIMARY KEY (paper_id, category_id)
);

CREATE TABLE edges (
  src_paper  uuid REFERENCES papers(id) ON DELETE CASCADE,
  dst_paper  uuid REFERENCES papers(id) ON DELETE CASCADE,
  type       text NOT NULL CHECK (type IN ('cites','concept')),
  weight     real DEFAULT 1.0,
  confirmed  boolean DEFAULT false,
  note_id    uuid REFERENCES notes(id) ON DELETE CASCADE,
  PRIMARY KEY (src_paper, dst_paper, type)
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON chunks (paper_id, page);
CREATE INDEX ON note_anchors (paper_id, page);
CREATE INDEX ON edges (dst_paper, type);
```

Choices that aren't obvious, so don't "fix" them:

- `tsv` is a generated column — BM25 stays in sync with no trigger to forget.
- `chunks.embedding` is nullable. A chunk exists after extraction; the embedding
  arrives a stage later. The pipeline needs that gap to be representable.
- `note_anchors` has a composite PK and no `id`. Anchoring a note twice to the same
  region is a bug; the PK prevents it for free.
- `edges.note_id` records *why* a concept edge exists. `confirmed` separates derived
  suggestions from edges the user approved.
- `cited_chunks` is a uuid array, not a join table — it's only ever read whole.
- `vector(768)` is fixed at the column. Changing the embedding model means a migration
  plus a full re-embed. That's accepted, not a problem to abstract away.

---

## Ingestion pipeline

One ARQ task, staged, writing status to the paper row after each stage so the UI can
show progress:

```
uploaded → extracting → chunking → embedding → enriching → ready
                                                        ↘ failed (+ status_error)
```

- **extracting** — PyMuPDF: text blocks with bboxes, page dimensions, page count.
  If the PDF has no text layer, fail loudly with a clear error rather than ingesting
  an empty document.
- **chunking** — section-aware when headings are detectable, sliding window with
  overlap otherwise. Pure functions in `core/chunking.py`. Every chunk records
  `strategy_ver`.
- **embedding** — batch through sentence-transformers. **Prefix chunks with
  `search_document:` and queries with `search_query:`.** Getting these backwards
  degrades retrieval with no visible error.
- **enriching** — OpenAlex lookup by DOI or title; write metadata and `cites` edges
  for referenced papers already in the library. Non-fatal: no DOI, no network, or
  rate-limited must still leave the paper usable.

The task must be **idempotent** — re-running deletes existing chunks for that paper
first. You will re-run it constantly while tuning chunking.

---

## Retrieval

One entry point, used by the chat endpoint and by MCP:

```python
async def retrieve(
    session, query: str, *,
    paper_ids: list[UUID] | None = None,
    category_id: UUID | None = None,
    k: int = 8,
) -> list[RetrievedChunk]
```

Scoping is a filter, not a separate code path — that's how "explain this paper" and
"compare these six papers" become the same function.

Pipeline:

1. Embed query (with `search_query:` prefix).
2. Vector top-30 — pgvector cosine, scoped.
3. BM25 top-30 — `ts_rank` against `tsv`, same scope.
4. Reciprocal rank fusion: `score(d) = Σ 1/(60 + rank_i(d))`. No score normalisation
   needed, which is why it beats weighted sums.
5. Cross-encoder rerank down to `k`.
6. **Diversity cap** for multi-paper scopes: max 2–3 chunks per paper, so one verbose
   paper can't crowd out the other five.

Write steps 1–2 first and return naive top-k. Add 3–6 later. The signature does not
change.

Write the two heavy queries (hybrid retrieval, recursive-CTE graph traversal) as raw
SQL via `session.execute(text(...))`. SQLAlchemy for everything ordinary. Do not build
a repository layer — SQLAlchemy is already the repository.

---

## Chat and citations

SSE endpoint. Emit **typed events, sources first**:

```
event: sources   {"chunks":[{"id":"C1","paper":"...","page":4,"bbox":[...]}]}
event: token     {"text":"..."}
event: done      {"llm_output_id":"..."}
```

Sources before tokens matters — the user sees what the model is reading while it's
still generating, and that's most of the trust the app earns.

Context assembly gives each chunk a citable ID:

```
[C1] (Smith 2023, p.4, Methods) <chunk text>
[C2] (Jones 2021, p.2, Results) <chunk text>
```

Instruct the model to cite `[C1]` inline. Parse the markers out of the stream, map
back to chunk UUIDs, and the frontend renders clickable citations that scroll the
reader and highlight the bbox.

Single-paper questions with a small paper: skip retrieval, send all its chunks.

Prompts live in `prompts/<name>.v<N>.md`, loaded by name and version, with the version
written into `llm_outputs.prompt_version`. Never f-strings scattered through code.

---

## Provenance rules

Implemented in `core/notes.py`, nowhere else:

- LLM responses are written to `llm_outputs`, never directly into `notes`.
- The user *promotes* a fragment into a note. That note gets `provenance='llm'` and
  `source_id` pointing at the output.
- Editing an `llm` note flips it to `llm_edited`.
- Notes created through MCP get `provenance='llm'`.
- The UI shows provenance on every note — a badge and a distinct background.

---

## MCP server

Separate process, run over stdio by the client, importing `backend.app.core` directly
with its own session. Not in Docker Compose — the transport is a process pipe.

```python
@mcp.tool()
async def search_library(query: str, category: str | None = None) -> list[dict]
@mcp.tool()
async def get_paper(paper_id: str) -> dict
@mcp.tool()
async def create_note(body: str, paper_id: str, quoted_text: str) -> dict
@mcp.tool()
async def related_papers(paper_id: str, hops: int = 1) -> list[dict]
```

Two rules:

- **Return IDs and structure, not prose.** A tool that summarises is a worse copy of
  the chat endpoint and gives the client model nothing to reason over.
- **Validate and return recoverable errors.** `category` is an enum populated from
  real categories at startup. On a bad value, return
  `{"error":"unknown_category","available":[...]}` — an exception gives the model
  nothing to correct with; the valid options get a correct retry.

Each tool body should be ~3 lines: open session, call a `core` function, serialise.
If a tool has real logic, that logic belongs in `core/`.

---

## Docker

```yaml
services:
  db:        pgvector/pgvector:pg16   # volume: pgdata; healthcheck
  redis:     redis:7-alpine
  api:       build ./backend          # uvicorn; volumes: code, pdfs, hfcache
  worker:    build ./backend          # arq;     volumes: code, pdfs, hfcache
  frontend:  build ./frontend         # vite dev
```

- `api` and `worker` share one image, different commands. Do not build two.
- **Ollama runs on the host**, not in Compose. Docker Desktop can't reach the GPU on
  macOS. Set `OLLAMA_URL=http://host.docker.internal:11434`.
- **Mount an HF cache volume** (`hfcache:/root/.cache/huggingface`) or every rebuild
  re-downloads the embedding and reranker models.
- **Multi-stage Dockerfile**: dependencies in one layer, code in another. The torch
  install is ~2GB; sharing a layer with your source means a full reinstall on every
  code change.
- `depends_on` waits for start, not readiness. Give the worker connection retry, or
  use `condition: service_healthy`.
- PDFs on a named volume, path in Postgres. No object store.

---

## Model manager (settings page)

Proxy Ollama's own API — no Docker socket, no container orchestration.

- `GET /api/tags` → list installed models
- `POST /api/pull` → streams NDJSON progress; re-stream it to the frontend as SSE
- `DELETE /api/delete` → remove a model

Treat the two model types differently in the UI:

- **Generation model** — a dropdown, takes effect immediately, no consequences.
- **Embedding model** — locked once papers are ingested. Show
  `indexed with nomic-embed-text-v1.5 · 12,400 chunks` with a separate
  "re-index library" action behind a confirmation. Changing it silently would
  invalidate every vector in the database.

Do **not** mount the Docker socket to let the frontend start arbitrary containers.
Socket access is root on the host, and "any image" implies no common API to talk to.

---

## Evaluation harness

`evals/questions.yaml` — 20 questions, each with the chunk IDs that should have been
retrieved. `evals/run.py` prints recall@k. About 20 lines of code.

Build it at step 4 and run it before and after every retrieval change. Without it,
"reranking feels better" is the most you will ever be able to say, and half the time
it will be wrong.

---

## Build order

1. Compose up, Alembic migration, one route that writes and reads a vector.
   **Nothing else until this works** — async SQLAlchemy + asyncpg + pgvector has
   sharp edges around type registration, and debugging it later while three other
   things are half-built is miserable.
2. Upload → worker → extract → chunks with bboxes in Postgres. No embeddings yet.
   Verify bboxes by rendering rectangles over a page.
3. Frontend: PDF.js viewer, text selection, highlight → note. **No LLM anywhere yet.**
   If this doesn't feel good to use, stop and fix it before building on top.
4. Embeddings, naive top-k retrieval, SSE chat scoped to one paper, citations that
   scroll the reader. Eval harness.
5. Categories, cross-paper retrieval.
6. MCP server.
7. Graph view — citation edges first (free from OpenAlex), concept edges after.
8. Hybrid retrieval + reranking, measured against the eval set.
9. Model manager.

Steps 1–3 contain no AI at all, deliberately. Everything later depends on the anchor
plumbing being right, and a bbox bug found at step 7 means redoing step 2 and half of
step 4.

---

## Explicitly out of scope

Do not build these. Each costs a week and teaches nothing new here.

- Authentication, users, multi-tenancy
- A dedicated vector database (Qdrant, Pinecone, Chroma) — Postgres does it
- A graph database — recursive CTEs handle thousands of edges fine
- Object storage / MinIO — a Docker volume is enough
- A repository layer over SQLAlchemy
- A plugin system for LLM providers — two adapters and an env var
- Multi-model embedding abstraction — one model, migrate when you change it
- Docker socket access from the API
- Kubernetes, CI/CD, production deployment
- Unsupervised LLM-generated concept edges — derive from note co-occurrence and
  require confirmation. A research tool that invents plausible connections that
  don't exist is worse than useless.

---

## Known traps

- `async_sessionmaker(expire_on_commit=False)`. The default expires objects after
  commit; touching an attribute afterwards triggers a lazy load, which in async
  context raises `MissingGreenlet` rather than just being slow.
- Use explicit `selectinload()` for relationships. Async SQLAlchemy can't lazy-load
  transparently — implicit access fails at runtime.
- One blocking call in an async route stalls the whole event loop. Anything CPU-bound
  (embedding, reranking on large batches, extraction) belongs in the worker.
- Load the embedding model once at worker startup, not per task.
- Three coordinate systems in the reader: PDF points, rendered canvas pixels, DOM
  position after zoom. Store PDF points and page dimensions; convert at render time.
  Get this right at step 2.
- Generate frontend types from FastAPI's OpenAPI schema (`openapi-typescript`) as a
  build step, from day one.
