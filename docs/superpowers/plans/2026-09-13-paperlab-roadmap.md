# PaperLab Roadmap

> **For agentic workers:** This is the master plan. It does not contain tasks. Each milestone gets its own
> task-by-task plan in this folder, written with superpowers:writing-plans when the milestone starts, and
> executed with superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Build PaperLab, a local-first research reader where the note is the primary object, following the brief's build order as revised by addendum 1 (M1–M12, with half-steps).

**Architecture:** FastAPI + async SQLAlchemy on Postgres/pgvector, an ARQ worker for ingestion, and a React/Vite frontend using PDF.js. Domain logic lives in `backend/app/core` with no FastAPI imports, so the MCP server (M6) can reuse it. Every LLM output is stored apart from human writing and is marked in the UI.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres 16 + pgvector, ARQ + Redis, PyMuPDF, sentence-transformers, Ollama, OpenAlex API, React 19 + TypeScript + Vite 8, PDF.js 6, react-force-graph, FastMCP, igraph or networkx for Leiden (chosen in M10).

**Spec:** [docs/superpowers/specs/2026-09-13-paperlab-brief.md](../specs/2026-09-13-paperlab-brief.md), amended by [addendum 1](../specs/2026-09-13-paperlab-brief-addendum-1.md). Where they conflict, the addendum wins.

## Global Constraints

These apply to every milestone plan. Values are copied from the spec.

- Single user, one machine: no auth, no multi-tenancy, no cloud deployment.
- `grep -r "fastapi" backend/app/core/` returns nothing.
- Every piece of LLM-generated text is stored separately from what the human wrote (`llm_outputs`) and is visibly marked in the UI (badge + distinct background on every note).
- Provenance rules are implemented in `backend/app/core/notes.py`, nowhere else.
- `vector(768)` with `nomic-embed-text-v1.5`; chunks embed with the `search_document:` prefix, queries with `search_query:`.
- Ingestion is one idempotent ARQ task writing `status` after each stage: `uploaded → extracting → chunking → embedding → enriching → ready`, or `failed` with `status_error`.
- Heavy queries (hybrid retrieval, recursive-CTE graph traversal) are raw SQL via `session.execute(text(...))`; SQLAlchemy for everything else; no repository layer.
- Prompts live in `backend/prompts/<name>.v<N>.md`; the version is written to `llm_outputs.prompt_version`.
- Out of scope: auth, dedicated vector DB (settled, see addendum §1), graph DB, object storage, repository layer, LLM provider plugin system, multi-model embedding abstraction, Docker socket access, Kubernetes/CI/CD, unsupervised LLM-generated concept edges.
- Also out of scope (addendum §8): full GraphRAG or LLM entity extraction over paper chunks; parsing the references section from PDF text, and GROBID; author name-matching or custom disambiguation; transitive reference expansion; merging topics into categories; a facet schema designed before real use.
- OpenAlex enrichment is always non-fatal. A paper with no match stays fully usable. Requests send `mailto`, ID lookups are batched (`filter=openalex_id:A|B|C&per-page=50`), and author records are not refetched within 30 days (`fetched_at`).
- Authors are keyed on OpenAlex ID/ORCID, never on name strings. `paper_topics` (external facts) and `categories` (the user's structure) stay separate tables.
- References are never imported without an explicit per-reference user action, and only one hop out.
- Ollama runs on the host (`OLLAMA_URL=http://host.docker.internal:11434`), not in Compose.
- Frontend types are generated from FastAPI's OpenAPI schema with `openapi-typescript`.

---

## How we work

Every milestone follows the same loop. Skills are named exactly as they are invoked.

1. **Plan:** `superpowers:writing-plans` writes `docs/superpowers/plans/YYYY-MM-DD-mN-<slug>.md`.
   Spike unfamiliar library APIs in the scratchpad *before* writing plan code. In M3 this caught three API surprises before any task was written.
   Run `superpowers:brainstorming` first only when the brief leaves real product decisions open (likely M4 chat UX, M7 graph UX, M7.5 references panel UX, and the M12 facet schema).
2. **Isolate:** `superpowers:using-git-worktrees` creates branch `mN-<slug>`.
   Compose has a fixed project name (`paperlab`). Run `cp .env.example .env` and `docker compose up -d --build` from the worktree root so bind mounts point at the worktree. Run it again from the main checkout after merging.
3. **Execute:** `superpowers:subagent-driven-development`. Use `superpowers:test-driven-development` for each task and `superpowers:systematic-debugging` for anything unexpected.
4. **Verify:** `superpowers:verification-before-completion`. Run the milestone's exit-criteria commands below and read the output before ticking anything.
5. **Review:** `superpowers:requesting-code-review`. Optionally add `ponytail:ponytail-review` for over-engineering.
6. **Finish:** `superpowers:finishing-a-development-branch`, then update this file (board, decision log, known issues).

Backend work also follows the project skill at `.claude/skills/fastapi` (see D17 for what is and isn't adopted).

### Commands

| What | Command |
|---|---|
| Start/refresh the stack | `docker compose up -d --build` |
| Backend tests (needs the compose DB on :5433) | `cd backend && uv run pytest` |
| Backend lint | `cd backend && uv run ruff check .` |
| Core invariant | `grep -r fastapi backend/app/core/` (must print nothing) |
| Regenerate frontend API types (API running) | `cd frontend && npm run gen:api` |
| Frontend type check / unit tests | `cd frontend && npx tsc -b && npm test` |
| End-to-end (whole stack running) | `cd frontend && npm run e2e` |

Commits use `<type>: <description>` (feat, fix, refactor, docs, test, chore, perf, ci) with no attribution trailer.

---

## Milestone board

| # | Milestone | Status | Plan |
|---|---|---|---|
| M1 | Stack, migration, vector round-trip | ✅ Done (uncommitted; committed by M3 Task 0) | none, built before the roadmap existed |
| M2 | Upload → worker → extract → chunks with bboxes | ✅ Done (uncommitted; committed by M3 Task 0) | none, built before the roadmap existed |
| M3 | Reader: PDF.js, selection, highlight → note | ⏭ Next | [2026-09-13-m3-reader-and-notes.md](2026-09-13-m3-reader-and-notes.md) |
| M4 | Embeddings, naive retrieval, SSE chat (one paper), citations, eval harness | Planned | written when M3 is merged |
| M5 | Categories, cross-paper retrieval | Planned | |
| M6 | MCP server | Planned | |
| M6.5 | Enrichment: authors, topics, paper metadata, retraction banner | Planned | |
| M7 | Graph view: citation, then co-author, then topic edges | Planned | |
| M7.5 | References panel: external refs, ranking, import, citing works | Planned | |
| M8 | Hybrid retrieval + reranking, measured | Planned | |
| M8.5 | Query router, then map-reduce | Planned | |
| M9 | Model manager | Planned | |
| M10 | Community detection + summaries | Planned | needs a real corpus |
| M11 | Concept extraction from notes | Planned | needs a real corpus |
| M12 | Facets + comparison table | Blocked until 30+ papers have been read in the app | |

Author page UI (addendum §6b) is a read-only view over M6.5 data and has no build-order slot. Schedule it whenever it's wanted.

---

## Milestones

### M1: Stack, migration, vector round-trip ✅

- Compose: `db` (pgvector/pg16, host port 5433), `redis`, `api` (:8000, runs `alembic upgrade head` on start), `worker`.
- Migration `0001` creates the full schema from the spec.
- **Exit criteria (met 2026-09-13):** `curl localhost:8000/api/health` returns `{"orm_roundtrip":true,"raw_sql_nearest_is_self":true}`; `alembic downgrade base && alembic upgrade head` runs cleanly.

### M2: Ingestion without embeddings ✅

- `POST /api/papers` (upload), `GET /api/papers[/{id}]`, `GET /api/papers/{id}/chunks?page=`, `POST /api/papers/{id}/reingest`.
- Worker stages `extracting → chunking → ready`. The `embedding` and `enriching` stages arrive in M4 and M6.5.
- **Exit criteria (met 2026-09-13):** two arXiv papers (single- and two-column) reach `ready`. An image-only PDF ends `failed` with a clear error. Chunk bboxes drawn over rendered pages line up with the text. `uv run pytest` passes.

### M3: Reader and notes (no AI)

- **Backend:** notes CRUD with provenance rules in `core/notes.py`; `GET /api/papers/{id}/file`; `DELETE /api/papers/{id}`.
- **Frontend:** Vite app in compose (:5180); generated API types; library page (upload, status, delete); PDF.js reader with zoom; selection → note composer; highlights; notes panel with provenance badge; click a note to scroll to it.
- **Exit criteria:**
  - `cd backend && uv run pytest`: all pass.
  - `cd frontend && npx tsc -b && npm test`: clean.
  - `cd frontend && npm run e2e`: highlight-to-note spec passes against the real stack.
  - You (the human) sign off the "does it feel good to use" checkpoint (M3 Task 7). **The brief says stop and fix before building on top.**

### M4: Embeddings, naive retrieval, single-paper chat, eval harness

- **Scope:**
  - `embedding` ingest stage. Load the model once at worker startup; `search_document:` prefix; batch.
  - `core/retrieval.py`: `retrieve(session, query, *, paper_ids=None, category_id=None, k=8)` doing vector top-k only.
  - `providers/llm.py` with the Ollama adapter and an optional Anthropic adapter; `providers/base.py` Protocol (now there are two implementations).
  - SSE chat scoped to one paper with events `sources → token → done`. Use FastAPI's `fastapi.sse.EventSourceResponse` (per the fastapi skill).
  - Small papers skip retrieval.
  - `[C1]` citation parsing; clicking a citation scrolls the reader and highlights the bbox.
  - `llm_outputs` rows with `prompt_version`; `prompts/*.v1.md`.
  - Promote a response fragment into a note (`provenance='llm'`, `source_id`).
  - `evals/questions.yaml` (20 questions) and `evals/run.py` printing recall@k.
- **Exit criteria:**
  - Recall@k baseline recorded in this file.
  - Chat on a paper streams sources before tokens.
  - A promoted note shows the AI badge; editing it flips the badge to "AI · edited".
- **Carried in:** K2, K3 (decide using eval numbers), D10 (chunk ↔ anchor resolution).

### M5: Categories and cross-paper retrieval

- **Scope:**
  - Category tree CRUD (`UNIQUE NULLS NOT DISTINCT`, see D4).
  - Tag notes and papers.
  - `retrieve` scoped by `category_id` or multiple `paper_ids`, with the diversity cap (max 2–3 chunks per paper). The cap lands here because this is the first multi-paper scope.
  - Category page = notes tagged with the category.
- **Exit criteria:** eval recall@k does not regress; a multi-paper question cites chunks from at least two papers.

### M6: MCP server

- **Scope:**
  - `mcp_server/server.py` (FastMCP, stdio) importing `app.core`.
  - Tools: `search_library`, `get_paper`, `create_note`, `related_papers`.
  - Recoverable errors (e.g. `{"error":"unknown_category","available":[...]}`).
  - MCP notes get `provenance='llm'`.
- **Exit criteria:**
  - Claude Desktop can search the library and create a note.
  - The note shows the AI badge in the reader, anchored on the right passage.
  - Each tool body stays at about 3 lines.
- **Carried in:** Q1.

### M6.5: Enrichment: authors, topics, paper metadata

- **Scope** (addendum §4, §6):
  - `enriching` ingest stage. Look up OpenAlex by DOI. With no DOI, search by `title.search` and accept the match only if year and first author agree. Non-fatal.
  - Metadata written onto the paper: title, abstract, year, venue, `type`, `is_retracted`, OA status and best OA location, `cited_by_count`, `referenced_works_count`, `primary_location`.
  - `authors` + `paper_authors` from `authorships` (position, corresponding flag, institution at time of publication on the join), plus one batched `/authors` fetch honouring the 30-day `fetched_at` cache.
  - `paper_topics` from author keywords, venue terms and OpenAlex concepts/topics, keeping `source` and `score`.
  - Fallback: PyMuPDF embedded metadata, then manual correction of metadata in the UI.
  - Reader: a prominent banner when `is_retracted`.
- **Exit criteria:**
  - A paper with a DOI gets authors (with OpenAlex IDs), topics and metadata.
  - A paper with no OpenAlex match still reaches `ready`.
  - With OpenAlex unreachable, ingestion still reaches `ready`.
  - A retracted paper shows the banner.
- **Carried in:** K1 (titles from OpenAlex), Q3.

### M7: Graph view

- **Scope:**
  - `cites` edges for papers already in the library (OpenAlex `referenced_works` matched on `openalex_id`).
  - `core/graph.py` recursive CTE.
  - react-force-graph view with citation edges first, then `co_authored` (via `paper_authors`), then `shares_topic` (via `paper_topics`, also used to colour nodes).
- **Exit criteria:**
  - A paper whose references are in the library shows citation edges.
  - Co-author and topic edge layers can be toggled.
- **Carried in:** Q2. Concept edges moved to M11 (D20).

### M7.5: References panel

- **Scope** (addendum §3):
  - `external_refs` + `paper_references`, fetched only for papers in the library.
  - Ranking: co-citation within the library, then proximity to note embeddings, then OA availability, then `cited_by_count` as a tiebreaker.
  - Summary line, e.g. "12 cited by 3+ library papers, 8 have PDFs".
  - Import: an ARQ job fetches `oa_pdf_url`, runs the normal pipeline, and sets `imported_as` on `ready`. Closed access shows the DOI link plus manual drop. No transitive expansion.
  - Citing-works direction (`cited_by`) in the same UI, newest first.
  - External-ref authors go into the same `authors` table.
- **Exit criteria:**
  - A reference cited by two library papers ranks above an uncited famous one.
  - Importing an OA reference marks it in-library for every paper that cites it.
  - Importing does not fetch the imported paper's references until the user asks.

### M8: Hybrid retrieval and reranking

- **Scope:** BM25 top-30 via `ts_rank`, reciprocal rank fusion (`Σ 1/(60 + rank)`), `bge-reranker-v2-m3` cross-encoder rerank to `k`. The `retrieve` signature stays unchanged.
- **Exit criteria:** eval recall@k before/after is recorded here. Keep only the steps that measurably help.

### M8.5: Query router and map-reduce

- **Scope** (addendum §2a–b):
  - Router prompt returning `{type: local|per_paper|global, scope: {paper_ids | category_id}}`.
  - Map: per paper, concurrently under a semaphore, `retrieve(paper_ids=[id], k≈6)` and extract `{paper_id, answer, supporting_chunk_ids, status: found|absent}`.
  - Reduce: synthesise over the structured records.
  - Cache map results on `(paper_id, sub_question_hash, prompt_version)`.
  - `global` uses map-reduce until facets (M12) and communities (M10) exist.
- **Exit criteria:**
  - A "compare these N papers" question produces a record for every paper in scope, with `absent` papers named in the answer.
  - A repeated sub-question hits the cache.

### M9: Model manager

- **Scope:**
  - Proxy Ollama `GET /api/tags`, `POST /api/pull` (NDJSON re-streamed as SSE), `DELETE /api/delete`.
  - Generation model dropdown.
  - Embedding model locked once papers exist ("indexed with … · N chunks"), with re-index behind a confirmation.
- **Exit criteria:**
  - Pulling a model shows live progress.
  - The embedding model cannot be switched silently.

### M10: Community detection and summaries

- **Scope** (addendum §5b):
  - Build the graph with zero LLM calls. Nodes: papers, topics, notes, categories, authors. Edges: `cites`, `shares_topic`, `co_anchored`, `same_category`, `co_authored`.
  - Run Leiden.
  - `communities` table, with one summary LLM call per community over abstracts and the user's notes.
  - Mark communities `is_stale` on material graph changes. Recompute on demand, not on every import.
- **Exit criteria:**
  - Recompute on the real library takes seconds, excluding summaries.
  - Summaries are marked as LLM output in the UI.

### M11: Concept extraction from notes

- **Scope** (addendum §5c): an LLM extracts concepts from **notes only**, producing `concept` edges with `note_id` set and `confirmed=false` until the user approves them.
- **Exit criteria:**
  - No concept is extracted from paper chunks.
  - No unconfirmed concept edge renders as confirmed.

### M12: Facets

- **Gate:** 30+ papers read in the app. Design the facet list from that usage, not from the addendum's starter list.
- **Scope** (addendum §2c):
  - `paper_facets` extraction with evidence chunks.
  - Per-category comparison table.
  - User corrections that persist and are never overwritten by re-extraction. Corrections must satisfy the LLM/human provenance constraint.
  - The `global` router path uses facets.

---

## Decision log

Newest last. Entry format: decision, then why. Don't reverse one without adding a new entry.

| ID | Date | Decision | Why |
|---|---|---|---|
| D1 | 2026-09-13 | `bbox` is a **list of rects**, one per text block (chunks) or per selected line (anchors), in PDF points with top-left origin | A single enclosing rect for a chunk spanning two columns covers the whole page width, so the highlight is useless |
| D2 | 2026-09-13 | Page numbers are 1-based everywhere | Matches PDF.js `getPage(n)` and human citations |
| D3 | 2026-09-13 | Chunks never cross a page boundary | Keeps each chunk's anchor on one page; a paragraph split across pages becomes two chunks |
| D4 | 2026-09-13 | `categories` uses `UNIQUE NULLS NOT DISTINCT (parent_id, name)` | Plain `UNIQUE` lets two root categories share a name, because NULLs are distinct |
| D5 | 2026-09-13 | No `pgvector.asyncpg.register_vector`; raw SQL binds vectors with `bindparam(name, type_=Vector(768))` | asyncpg falls back to text I/O for the vector type; verified by `/api/health` on both the ORM and `text()` paths |
| D6 | 2026-09-13 | Worker runs under the `watchfiles` CLI, not `arq --watch` | `arq --watch` restarts in-process and never re-imports changed code |
| D7 | 2026-09-13 | Heading detection is a font heuristic; body blocks need ≥ 4 words; hyphenated line breaks are rejoined by `join_lines` | PyMuPDF's `TEXT_DEHYPHENATE` does nothing in dict mode; figure labels and page numbers were leaking into chunks |
| D8 | 2026-09-13 | `note_anchors` is a SQLAlchemy Core `Table`, not a mapped class | Its PK includes the jsonb `bbox`; the ORM identity map can't hash a list |
| D9 | 2026-09-13 | Deleting a paper keeps its notes (anchors cascade away) | The note is the primary object; silently deleting human writing is data loss |
| D10 | 2026-09-13 | `note_anchors.chunk_id` is left NULL in M3 | Re-ingest deletes chunks (`ON DELETE SET NULL`), so a stored link goes stale; resolve chunk ↔ anchor by page + rect overlap when M4/M6 need it |
| D11 | 2026-09-13 | A note body may be empty | A plain highlight is a valid note; the quote carries the content |
| D12 | 2026-09-13 | `openapi-typescript@7.13.0` runs via `npx`, not as a devDependency | Its peer dependency `typescript@^5` conflicts with the Vite template's TypeScript 6 |
| D13 | 2026-09-13 | PDF.js is imported only through `frontend/src/features/reader/pdfjs.ts`; text layer via `TextLayerBuilder` | `pdf_viewer.mjs` needs `globalThis.pdfjsLib` set first, otherwise it crashes on import; `TextLayerBuilder` includes PDF.js's selection-jump fix |
| D14 | 2026-09-13 | Hash routing and plain `fetch` + `useState`; no router or data-fetching library in M3 | Two views and a handful of calls; revisit when chat/graph/settings add real routing or cache needs |
| D15 | 2026-09-13 | Backend DB tests run against the compose Postgres inside a rolled-back transaction (`join_transaction_mode="create_savepoint"`) | Real Postgres and pgvector without maintaining a second database; a service's own `commit()` stays inside the test |
| D16 | 2026-09-13 | Frontend is published on host port **5180** | 5173 is already taken on this machine |
| D17 | 2026-09-13 | FastAPI skill conventions adopted: `Annotated` dependency aliases (`SessionDep`), return-type response models, `fastapi.sse.EventSourceResponse` for SSE. **Not** adopted: SQLModel, Asyncer, the `fastapi dev` CLI | The brief mandates SQLAlchemy for pgvector; `asyncio.to_thread` is stdlib; compose already runs `uvicorn --reload` |
| D18 | 2026-09-13 | Ruff with rules `E,F,I`, line length 120 | Catches real errors and import order without reformatting the codebase |
| D19 | 2026-09-13 | Brief addendum 1 adopted. It adds M6.5, M7.5, M8.5, M10–M12, rejects full GraphRAG, and re-confirms no vector DB | Global questions and reference discovery; community detection runs on the real graph at ~1% of GraphRAG's cost; filtered similarity search belongs in Postgres |
| D20 | 2026-09-13 | The `enriching` stage moves from M7 to M6.5. Concept edges move from M7 to M11, where the LLM extracts them from notes and the user confirms them | Addendum build order: M7 is citation, co-author and topic edges only; concept extraction needs a real corpus of notes |

## Open questions and known issues

| ID | Issue | Resolve in |
|---|---|---|
| Q1 | MCP `create_note(body, paper_id, quoted_text)` has no page/bbox, but the `note_anchors` PK makes both NOT NULL. Proposal: locate `quoted_text` in the paper's chunks to derive page + rects | M6 |
| Q2 | `edges.type='cites'` (M7) overlaps `paper_references` + `external_refs.imported_as` (M7.5). Decide whether in-library citation edges stay stored or are derived from the references tables. Similarly, derive `shares_topic`/`co_authored`/`co_anchored`/`same_category` at query time rather than storing them | M7 / M7.5 |
| Q3 | `papers.authors` jsonb duplicates `authors`/`paper_authors`. Decide whether to drop it or keep it for papers with no OpenAlex record, since manual author entry must not invent name-keyed authors | M6.5 |
| K1 | The title heuristic keeps only the first line of multi-line titles (e.g. "BERT: … Transformers for") | M6.5 (OpenAlex metadata) |
| K2 | Heading false positives in front matter (author names, second title line, bold bullets) | M4: measure with evals before tuning |
| K3 | References-section chunks are indexed and may pollute retrieval | M4/M8: decide with eval numbers |
| K4 | Pages assume rotation 0 (`providers/extraction.py`) | When a rotated PDF shows up |
| K5 | Frontend bundle > 500 kB because of pdfjs | Only if it matters; local app |
| K6 | `.claude/skills/fastapi/` is an untracked project skill that is not part of the baseline commit | Owner decides whether to commit it |
