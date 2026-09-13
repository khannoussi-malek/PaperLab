# PaperLab Roadmap

> **For agentic workers:** This is the master plan. It does not contain tasks. Each milestone gets its own
> task-by-task plan in this folder, written with superpowers:writing-plans when the milestone starts, and
> executed with superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Build PaperLab, a local-first research reader where the note is the primary object, following the brief's build order as revised by addendum 1 (M1–M12, with half-steps).

**Architecture:** FastAPI + async SQLAlchemy on Postgres/pgvector, an ARQ worker for ingestion, and a React/Vite frontend using PDF.js. Domain logic lives in `backend/app/core` with no FastAPI imports, so the MCP server (M6) can reuse it. Every LLM output is stored apart from human writing and is marked in the UI.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres 16 + pgvector, ARQ + Redis, PyMuPDF, sentence-transformers, Ollama, OpenAlex API, React 19 + TypeScript + Vite 8, shadcn/ui on Tailwind CSS 4, TanStack Query, lucide-react, PDF.js 6, react-force-graph, FastMCP, igraph or networkx for Leiden (chosen in M10).

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
- **Frontend UI (D24):**
  - Build UI from shadcn/ui components (`frontend/src/components/ui/`, added with `npx shadcn@4.21.0 add` or the shadcn MCP server in `.mcp.json`) and Tailwind utility classes.
  - No per-feature `.css` files: the only stylesheets are `frontend/src/index.css` (tokens) and PDF.js's `pdf_viewer.css`.
  - Server state goes through TanStack Query hooks in `frontend/src/api/queries.ts`.
  - Light, dark and system themes are all supported. The PDF page stays white.
  - `frontend/design-system/MASTER.md` (derived from the `ui-ux-pro-max` skill) holds the tokens and rules.

---

## How we work

Every milestone follows the same loop. Skills are named exactly as they are invoked.

1. **Plan:** `superpowers:writing-plans` writes `docs/superpowers/plans/YYYY-MM-DD-mN-<slug>.md`.
   Spike unfamiliar library APIs in the scratchpad *before* writing plan code. In M3 this caught three API surprises before any task was written.
   Run `superpowers:brainstorming` first only when the brief leaves real product decisions open (likely M4 chat UX, M7 graph UX, M7.5 references panel UX, and the M12 facet schema).
2. **Branch:** in the project folder itself, `git switch -c mN-<slug>`. No git worktrees (D25). A second milestone running in parallel uses a sibling clone instead (D27, see "Parallel tracks").
   The compose stack keeps running from the project folder; after adding frontend dependencies, run `docker compose up -d --build -V frontend`.
3. **Execute:** `superpowers:subagent-driven-development`. Use `superpowers:test-driven-development` for each task and `superpowers:systematic-debugging` for anything unexpected.
4. **Verify:** `superpowers:verification-before-completion`. Run the milestone's exit-criteria commands below and read the output before ticking anything.
5. **Review:** `superpowers:requesting-code-review`. Optionally add `ponytail:ponytail-review` for over-engineering.
6. **Finish:** `superpowers:finishing-a-development-branch`, then update this file (board, decision log, known issues).

Backend work also follows the project skill at `.claude/skills/fastapi` (see D17 for what is and isn't adopted).

UI work follows `ui-ux-pro-max`:
- **Planning a new screen or component** (M4 chat, M7 graph, M7.5 references panel, M7.6 watches, M9 settings, M12 comparison table): run the skill's `search.py … --domain ux` / `--domain style` for the pattern, then fold any new tokens or rules into `frontend/design-system/MASTER.md` before writing plan code. Pick components through the shadcn MCP server.
- **Every UI task:** starts by reading `MASTER.md` and ends with its "Pre-delivery check" in both themes. That check is extra; it never replaces a test.

### Testing policy

Every milestone's exit criteria implicitly include these:

- **Coverage gate:** `uv run pytest --cov` passes. The 80% threshold lives in `pyproject.toml`.
- **Real Postgres:** tests hit the compose Postgres inside a rolled-back transaction (D15). Don't mock the database.
- **Fakes at the edges only:** tests never call an external service.
  - Redis/ARQ: `FakeArq` (the `arq` fixture).
  - OpenAlex (M6.5, M7.5): `httpx.MockTransport` serving recorded JSON. Include a no-match case and a network-error case, since enrichment must stay non-fatal.
  - Ollama/LLM (M4+): a fake adapter implementing the provider Protocol.
- **Real files:** ingestion is tested end to end through `ingest_paper` with PDFs generated in `conftest.py`, including an ingest re-run and a failure path.
- **Checked automatically:** `tests/test_invariants.py` enforces the no-fastapi-in-core rule and round-trips every migration (upgrade → downgrade → upgrade) on a throwaway database. A new migration is covered as soon as it exists.
- **Bug fixes:** the failing test comes first.
- **Retrieval quality** (M4, M8, M8.5) is measured by the eval harness, not by unit tests. Record recall@k in this file.
- **Frontend:** Vitest for pure logic (coordinates, routing, parsing), Playwright for critical flows against the real stack.

### Test requirements for milestone plans

The testing policy says *how* we test. These rules say what every milestone plan must contain, so no task ships untested. superpowers:writing-plans applies them when drafting; superpowers:requesting-code-review rejects a plan or branch that breaks one.

1. **Every task ends with automated tests for what it built**, and a step that runs them with the exact expected output. A task whose only check is manual is incomplete. Manual walkthroughs (like M3's "does it feel good") are extra and never replace a test.
2. **Red before green.** Each test is run and seen failing before the code exists, and the plan states the expected failure. When that's impossible (an E2E spec over UI an earlier task built), the plan adds a step that introduces a named deliberate bug, shows the spec failing, then undoes the bug.
3. **Cover every layer the milestone touches:**
   - Each `core` function: a service test with its error branches.
   - Each API route: an HTTP test for success and every error status it can return.
   - Each worker stage: tested through `ingest_paper` (or its job) with generated files, including a re-run and a failure.
   - Each migration: covered automatically by `tests/test_invariants.py`.
   - Each pure frontend function: a Vitest test.
   - Each user-visible flow: a Playwright spec on the real stack using the `paperId` fixture from `frontend/e2e/fixtures.ts`.
4. **Deterministic fakes wherever a real call would make a test flaky or cost money:**
   - LLM: a fake provider adapter, selectable by env var so the E2E stack uses it too (from M4).
   - OpenAlex, arXiv, Semantic Scholar, Ollama: `httpx.MockTransport` with recorded responses, including no-match, error and rate-limit cases.
   - Nothing in the test suites calls the network.
5. **The milestone's "Required tests" list below is the minimum.** Its plan maps each item to a task. An item may be dropped only with a decision-log entry saying why.
6. **Plan code is executed while the plan is written.** The plan states what was run and what was only predicted, as the M3 plan does.
7. **A milestone is done only when all suites are green in one run:**
   - `uv run pytest --cov` (≥ 80%).
   - `uv run ruff check .`
   - `npx tsc -b`
   - `npm test`
   - `npm run typecheck:e2e`
   - `npm run e2e`
   - For retrieval milestones, the eval harness with recall@k recorded here.

### Commands

| What | Command |
|---|---|
| Start/refresh the stack | `docker compose up -d --build` |
| Refresh the frontend after adding npm packages (renews the `node_modules` volume) | `docker compose up -d --build -V frontend` |
| Backend tests (needs the compose DB on :5433) | `cd backend && uv run pytest` |
| Backend tests + coverage gate (≥ 80%, run before finishing a milestone) | `cd backend && uv run pytest --cov` |
| Backend lint | `cd backend && uv run ruff check .` |
| Core invariant | `grep -r fastapi backend/app/core/` (must print nothing) |
| Regenerate frontend API types (API running) | `cd frontend && npm run gen:api` |
| Frontend type check / unit tests | `cd frontend && npx tsc -b && npm test` |
| E2E spec type check | `cd frontend && npm run typecheck:e2e` |
| End-to-end (whole stack running) | `cd frontend && npm run e2e` |

Commits use `<type>: <description>` (feat, fix, refactor, docs, test, chore, perf, ci) with no attribution trailer.

### Parallel tracks (D27)

The dependency graph decides what can run at once:

| Wave | Milestones | Unblocked by |
|---|---|---|
| 1 | M4 · M6.5 | M3 |
| 2 | M5, M8, M9 (after M4) · M7 (after M6.5) | wave 1 |
| 3 | M6 (M4 + M5) · M7.5 (M4 + M6.5) · M8.5 (M5) | wave 2 |
| 4 | M7.6 (M7.5) | wave 3 |
| Gated | M10, M11, M12 | a real corpus: the owner reading 30+ papers in the app, which can happen during any wave |

- **Track A** is the project folder and its stack (:5433 / :8000 / :5180).
- **Every other track** is a sibling clone `../research-note-mN` with its own compose project and shifted ports. It runs one Claude Code session per track, and that session runs subagent-driven-development for its tasks.
- **Clone setup** needs no tracked-file changes:
  - `git clone <project> ../research-note-mN`, then copy `.env` and `.claude/skills`.
  - Add `COMPOSE_PROJECT_NAME=paperlab-mN` to the clone's `.env`.
  - Add an untracked `docker-compose.override.yml` with `ports: !override [...]` per service, listed in `.git/info/exclude`.
  - Tests take the ports through `TEST_DATABASE_URL` and `E2E_BASE_URL`.
- **Merge order:** whichever track finishes first merges first. The second rebases onto main, renumbers its Alembic revision and its D-entries if they collide, and regenerates the API types.

---

## Milestone board

| # | Milestone | Status | Plan |
|---|---|---|---|
| M1 | Stack, migration, vector round-trip | ✅ Done | none, built before the roadmap existed |
| M2 | Upload → worker → extract → chunks with bboxes | ✅ Done | none, built before the roadmap existed |
| M3 | Reader: PDF.js, selection, highlight → note | ✅ Done (PR #1, merged 2026-09-13) | [2026-09-13-m3-reader-and-notes.md](2026-09-13-m3-reader-and-notes.md) |
| M4 | Embeddings, naive retrieval, SSE chat (one paper), citations, eval harness | ⏭ Wave 1, track A (project folder) | to be written |
| M5 | Categories, cross-paper retrieval | Planned (wave 2) | |
| M6 | MCP server | Planned (wave 3) | |
| M6.5 | Enrichment: authors, topics, paper metadata, retraction banner | ⏭ Wave 1, track B (`../research-note-m6.5`) | to be written |
| M7 | Graph view: citation, then co-author, then topic edges | Planned | |
| M7.5 | References panel: external refs, ranking, import, citing works | Planned | |
| M7.6 | Paper watch: saved searches, daily bot, ranked inbox | Planned | design: [paper-watch spec](../specs/2026-09-13-paper-watch-design.md) |
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
- **Frontend:**
  - Vite app in compose (:5180), with generated API types.
  - UI foundation (Task 4.5, D24): shadcn/ui + Tailwind, TanStack Query, a light/dark/system theme toggle, `design-system/MASTER.md`, and the shadcn MCP server.
  - Library page (upload, status, delete).
  - PDF.js reader with zoom.
  - Selection → note composer, highlights, and a notes panel with provenance badges; clicking a note scrolls to it.
- **Exit criteria:**
  - `cd backend && uv run pytest --cov && uv run ruff check .`: all pass, coverage ≥ 80%.
  - `cd frontend && npx tsc -b && npm test && npm run typecheck:e2e`: clean.
  - `cd frontend && npm run e2e`: every Playwright test passes against the real stack (11 at last count). A lower count means a test was skipped or deleted.
  - You (the human) sign off the "does it feel good to use" checkpoint (M3 Task 7). **The brief says stop and fix before building on top.**
- **Required tests** (all written and run in the M3 plan):
  - Backend:
    - `test_notes.py`: provenance flip, reading order, page range, unknown paper, delete keeps notes.
    - `test_notes_api.py`: every route's success path and its 404/422s.
    - `test_notes_edges.py`.
  - Vitest: `coords.test.ts` (conversions round-trip at any zoom), `route.test.ts`, `queries.test.ts` (library polls only while ingesting).
  - Playwright:
    - `library.spec.ts`: upload → ready → delete; non-PDF error; Retry after a failed first load (added by the M3 executor during Task 3 review).
    - `theme.spec.ts`: toggle to dark, survive reload, System follows the OS preference.
    - `reader-render.spec.ts`: canvas has ink; text layer inside PyMuPDF's chunk rect at 3 zooms; missing paper.
    - `highlight-to-note.spec.ts`: create + reload, zoom, edit keeps "You", delete, cross-page rejected.
  - Deliberate-bug checks: 7 breaks, each turning a named spec red (the library polling break re-proved on TanStack Query in Task 4.5).

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
- **Required tests:**
  - **Embedding stage (worker):**
    - Chunks are embedded with the `search_document:` prefix and queries with `search_query:`. A fake embedder records its inputs.
    - The model loads once per worker, not once per task.
    - A re-ingest replaces the vectors.
    - An embedder failure ends in `failed` with `status_error`.
  - **`retrieve`:** on seeded vectors it returns the true nearest k in order, respects `paper_ids`, and never returns chunks outside the scope.
  - **Small paper:** retrieval is skipped and all chunks are sent.
  - **Pure functions:**
    - Citation parser: `[C1]`, `[C1][C3]`, a marker split across two stream tokens, unknown `[C9]` ignored.
    - Context assembly: `[C1] (Author Year, p.N, Section)`.
    - Prompt loader: by name and version; a missing version raises.
  - **SSE chat, with the fake LLM:**
    - Events arrive in order `sources → token… → done`, and `sources` comes before the first token.
    - One `llm_outputs` row is written with `model`, `prompt_version` and `cited_chunks`.
    - An LLM error mid-stream emits an error event.
    - Chat never inserts into `notes`.
  - **Provenance:** a promoted fragment → `provenance='llm'` with `source_id`; editing it → `llm_edited`.
  - **Playwright, with the fake LLM:**
    - Sources render before the answer.
    - Clicking `[C1]` scrolls the reader to the cited page and highlights the chunk's rect.
    - A promoted note shows "AI"; after an edit it shows "AI · edited".
  - **Eval harness:** `evals/run.py` runs on a tiny seeded question set in the test suite; the real recall@k baseline is recorded in this file.

### M5: Categories and cross-paper retrieval

- **Scope:**
  - Category tree CRUD (`UNIQUE NULLS NOT DISTINCT`, see D4).
  - Tag notes and papers.
  - `retrieve` scoped by `category_id` or multiple `paper_ids`, with the diversity cap (max 2–3 chunks per paper). The cap lands here because this is the first multi-paper scope.
  - Category page = notes tagged with the category.
- **Exit criteria:** eval recall@k does not regress; a multi-paper question cites chunks from at least two papers.
- **Required tests:**
  - **Categories:**
    - Duplicate sibling names are rejected, including at the root (D4).
    - Deleting a parent removes its subtree.
    - Tagging a note or paper twice is a no-op.
    - Category routes: success and every error status.
  - **`retrieve` scoping:** `category_id` and multiple `paper_ids` return only in-scope chunks.
  - **Diversity cap:** with one dominant paper, at most 3 of the k chunks come from it.
  - **Playwright:** create a category, tag a note, and see the note on the category page; a multi-paper chat (fake LLM) cites chunks from two papers.
  - **Eval:** recall@k does not regress against the M4 baseline.

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
- **Required tests** (in-process FastMCP client against the real DB):
  - **`search_library`:** returns IDs and structure, not prose.
  - **Unknown category:** returns `{"error":"unknown_category","available":[...]}` with the real category names.
  - **`create_note`:**
    - Resolves page and rects from `quoted_text` (Q1) and stores `provenance='llm'`.
    - A quote not found in the paper returns a recoverable error.
  - **`get_paper` / `related_papers`:** unknown IDs return recoverable errors; `hops` is respected.
  - **Tool bodies:** `server.py` contains no SQL and imports only `app.core` services.
  - **Playwright:** a note created through MCP shows the AI badge in the reader, highlighted on the quoted passage.

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
- **Required tests** (OpenAlex via `httpx.MockTransport` with recorded JSON; no network):
  - **Matching:**
    - A DOI match fills metadata, authors (keyed by OpenAlex ID) and topics (with `source` and `score`).
    - The title-search fallback accepts a match only when year and first author agree; a mismatch is rejected.
  - **Never fatal:** no match, a network error, a timeout and HTTP 429 all still reach `ready`.
  - **Requests:**
    - Every request carries `mailto`.
    - Author fetches are batched (`filter=openalex_id:A|B|C&per-page=50`).
    - An author fetched under 30 days ago is not refetched; one older than that is.
  - **Authors:** two authors with the same name but different OpenAlex IDs stay two rows.
  - **Fallback:** PyMuPDF metadata is used when OpenAlex has nothing; a manual metadata correction persists.
  - **Playwright:** a retracted fixture paper shows the banner.

### M7: Graph view

- **Scope:**
  - `cites` edges for papers already in the library (OpenAlex `referenced_works` matched on `openalex_id`).
  - `core/graph.py` recursive CTE.
  - react-force-graph view with citation edges first, then `co_authored` (via `paper_authors`), then `shares_topic` (via `paper_topics`, also used to colour nodes).
- **Exit criteria:**
  - A paper whose references are in the library shows citation edges.
  - Co-author and topic edge layers can be toggled.
- **Carried in:** Q2. Concept edges moved to M11 (D20).
- **Required tests:**
  - **Graph CTE:**
    - `hops=1` and `hops=2` return exactly the expected nodes on a fixture graph.
    - Cycles terminate.
    - Edge-type filters work.
  - **Edges:**
    - `cites` edges exist only between papers matched on `openalex_id` in the library.
    - `co_authored` and `shares_topic` are derived correctly from `paper_authors` / `paper_topics`.
  - **Graph API:** payload shape and error statuses.
  - **Playwright:** the graph renders the fixture library's nodes and edges; toggling each layer changes the visible edge count.

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
- **Required tests** (OpenAlex mocked):
  - **Ranking:**
    - A reference cited by 2 library papers outranks an uncited one with a far higher `cited_by_count`.
    - Note-embedding proximity and OA availability break ties in the documented order.
    - The summary line counts are correct.
  - **Import (ARQ job, PDF download mocked):**
    - An OA reference runs the normal pipeline and sets `imported_as` for every citing paper.
    - A closed-access reference fetches nothing and offers the DOI link.
    - Importing a paper requests none of *its* references (no transitive expansion).
  - **Citing works:** listed newest first.
  - **Playwright:** open the references panel, import an OA reference, and see it marked in-library on both citing papers.

### M7.6: Paper watch

- **Spec:** [2026-09-13-paper-watch-design.md](../specs/2026-09-13-paper-watch-design.md). Brainstorming is done; go straight to writing-plans after spiking the three APIs.
- **Scope:**
  - `watches` + `watch_hits` tables; `external_refs` gains `arxiv_id`, `s2_id`, `abstract`, `published_on`.
  - ARQ cron (`run_at_startup=True`) enqueues one `run_watch` per watch not checked in 20 h.
  - `run_watch` fetches OpenAlex, arXiv and Semantic Scholar since the watermark (7-day overlap), merges on shared IDs, drops library papers, ranks by embedding similarity to the query + notes.
  - Watermark advances only when every source succeeded.
  - Watches view: inbox capped at 20 per watch, Import (M7.5 job) / DOI link / Dismiss, nav unread badge.
  - Suggest only; never auto-import. No LLM calls.
- **Exit criteria:**
  - A new watch shows ranked hits from at least two sources after one run.
  - A second run adds no duplicates.
  - A blocked source shows its error, and its papers appear on the next clean run.
  - Importing a hit marks it in-library everywhere.
- **Required tests** (OpenAlex, arXiv and Semantic Scholar all mocked; clock controlled):
  - **Scheduling:** the cron enqueues `run_watch` only for watches not checked in 20 h.
  - **Merging and ranking:**
    - Results from all three sources merge on shared IDs into one `external_refs` row.
    - Library papers are dropped.
    - Ranking follows embedding similarity to the query plus the user's notes.
  - **Watermark and failures:**
    - Only a fully successful run advances the watermark, with the 7-day overlap.
    - A second run adds no duplicate hits.
    - A failing source records its error; its papers appear on the next clean run.
  - **Inbox:**
    - Capped at 20 per watch.
    - Dismiss persists.
    - Import goes through the M7.5 job and marks the hit in-library everywhere.
    - The unread badge count is correct.
  - **No LLM, no auto-import:** the fake LLM records zero calls, and no watch run creates a `papers` row.
  - **Playwright:** create a watch, run it against the mocked sources, see ranked hits, dismiss one, import one.

### M8: Hybrid retrieval and reranking

- **Scope:** BM25 top-30 via `ts_rank`, reciprocal rank fusion (`Σ 1/(60 + rank)`), `bge-reranker-v2-m3` cross-encoder rerank to `k`. The `retrieve` signature stays unchanged.
- **Exit criteria:** eval recall@k before/after is recorded here. Keep only the steps that measurably help.
- **Required tests:**
  - **Fusion and rerank (unit):**
    - RRF over known rank lists gives the hand-computed order.
    - BM25 respects the same scope filters as the vector search.
    - The reranker (fake scorer) reorders and cuts to `k`.
  - **Regression:** every existing `retrieve` test passes unchanged, since the signature must not change.
  - **Eval:** recall@k before and after each step is recorded here. A step that lowers recall is removed, not kept.

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
- **Required tests** (fake LLM):
  - **Router:** valid output selects `local` / `per_paper` / `global`; invalid JSON falls back to `local`.
  - **Map:**
    - Produces one record per paper in scope, including `absent` papers.
    - Concurrency never exceeds the semaphore (the fake records peak concurrency).
  - **Reduce:** the answer names the `absent` papers.
  - **Cache:** a repeated sub-question makes no new LLM call; a changed `prompt_version` misses the cache.

### M9: Model manager

- **Scope:**
  - Proxy Ollama `GET /api/tags`, `POST /api/pull` (NDJSON re-streamed as SSE), `DELETE /api/delete`.
  - Generation model dropdown.
  - Embedding model locked once papers exist ("indexed with … · N chunks"), with re-index behind a confirmation.
- **Exit criteria:**
  - Pulling a model shows live progress.
  - The embedding model cannot be switched silently.
- **Required tests** (Ollama via `httpx.MockTransport`):
  - **Proxy:** `tags`, `pull` (NDJSON progress re-streamed as SSE in order, including a mid-stream error line), and `delete` routes, each with its error statuses.
  - **Embedding model lock:**
    - Changing the model while chunks exist is refused.
    - Re-indexing requires the explicit confirmation flag and re-embeds every chunk.
  - **Playwright** (stub Ollama): pull progress renders live; the embedding selector is locked and shows "indexed with … · N chunks".

### M10: Community detection and summaries

- **Scope** (addendum §5b):
  - Build the graph with zero LLM calls. Nodes: papers, topics, notes, categories, authors. Edges: `cites`, `shares_topic`, `co_anchored`, `same_category`, `co_authored`.
  - Run Leiden.
  - `communities` table, with one summary LLM call per community over abstracts and the user's notes.
  - Mark communities `is_stale` on material graph changes. Recompute on demand, not on every import.
- **Exit criteria:**
  - Recompute on the real library takes seconds, excluding summaries.
  - Summaries are marked as LLM output in the UI.
- **Required tests:**
  - **Graph build:** zero LLM calls (the fake records none).
  - **Leiden:** with a fixed seed, a fixture graph gives the expected communities.
  - **Staleness:** material graph changes set `is_stale`; unrelated changes don't; recompute clears it.
  - **Summaries:** exactly one fake-LLM call per community, each stored as LLM output.
  - **Performance smoke:** recompute on a generated 1,000-node graph stays within the documented time.
  - **Playwright:** community summaries render with the AI badge.

### M11: Concept extraction from notes

- **Scope** (addendum §5c): an LLM extracts concepts from **notes only**, producing `concept` edges with `note_id` set and `confirmed=false` until the user approves them.
- **Exit criteria:**
  - No concept is extracted from paper chunks.
  - No unconfirmed concept edge renders as confirmed.
- **Required tests** (fake LLM):
  - **Extraction input:** the fake LLM receives note text only. The test asserts that no chunk text appears in any prompt.
  - **Created edges:** `type='concept'`, `note_id` set, `confirmed=false`.
  - **Confirming:** flips `confirmed`; rejecting removes the edge.
  - **Playwright:** unconfirmed concept edges render visibly distinct from confirmed ones; confirming one changes its style.

### M12: Facets

- **Gate:** 30+ papers read in the app. Design the facet list from that usage, not from the addendum's starter list.
- **Scope** (addendum §2c):
  - `paper_facets` extraction with evidence chunks.
  - Per-category comparison table.
  - User corrections that persist and are never overwritten by re-extraction. Corrections must satisfy the LLM/human provenance constraint.
  - The `global` router path uses facets.
- **Required tests:**
  - **Extraction** (fake LLM): stores evidence chunk IDs for every facet value.
  - **Corrections:**
    - A user correction survives re-extraction.
    - A corrected value carries human provenance; an uncorrected one stays LLM.
  - **`global` router path:** uses facets once they exist.
  - **Playwright:** the comparison table renders a category's papers × facets; a correction made in the table persists after reload.

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
| D21 | 2026-09-13 | M1–M2 backend test pack added (extraction, papers core + API, ingest worker, invariants, migration round-trip) with an 80% coverage gate. Coverage uses `core = "sysmon"` | The default C tracer drops route lines after an SQLAlchemy greenlet switch and under-reported the API at ~75%. A mutation check (6 deliberate breaks) confirmed each one fails a test |
| D22 | 2026-09-13 | M7.6 paper watch added: saved searches checked daily against OpenAlex, arXiv and Semantic Scholar, ranked by embeddings into an in-app inbox. Discovered papers are `external_refs` rows; the bot never imports | Keeps the user current without breaking the explicit-import rule; reusing `external_refs` means one row per paper whether a library paper cites it or a watch found it, so `imported_as` resolves both |
| D23 | 2026-09-13 | Every milestone plan must meet the "Test requirements for milestone plans" rules: every task ends with automated tests shown red first (or a deliberate-bug check when red-first is impossible); each milestone has a Required tests list; E2E specs are type-checked and run with `workers: 1` on a `paperId` fixture that always cleans up | Manual checks alone let broken work pass as done. In M3, 7 deliberate bugs were each caught by a named spec, so the tests demonstrably guard behaviour |
| D24 | 2026-09-13 | **Supersedes D14's "no data-fetching library".**<br>Frontend UI is shadcn/ui (style `radix-nova`, CLI 4.21.0) on Tailwind CSS 4, with lucide icons, TanStack Query for server state, and a light/dark/system theme.<br>Tokens and rules live in `frontend/design-system/MASTER.md`, derived from `ui-ux-pro-max`: slate + blue palette, Crimson Pro headings, Atkinson Hyperlegible body, bundled via `@fontsource`.<br>The shadcn MCP server is configured in `.mcp.json`.<br>Lands as M3 Task 4.5, before the reader and notes UI. Hash routing from D14 stays | The owner doesn't want hand-written HTML/CSS. Components we own (copied, not a runtime library), plus an MCP server agents can query, keep UI work fast and consistent.<br>TanStack Query replaces the manual polling, refresh and error state that every page would otherwise re-implement. Queries use `retry: false` because a local API fails immediately.<br>Doing it before Task 5 means only the 100-line Library page needed restyling |
| D25 | 2026-09-13 | Milestones are built on a branch in the project folder, not in a git worktree. M3 moved from `.claude/worktrees/m3-reader-notes` back into the project folder mid-milestone | The owner wants the code where they work. A worktree kept the code and the running stack somewhere else, which was confusing |
| D26 | 2026-09-13 | Subtle glassmorphism on the app chrome (toolbar, notes panel, library card, menus, alerts, hover card) over a faint blue/violet body glow. Tokens `glass`, `glass-strong`, `glass-border`, `ambient-1/2` in `index.css`; rules in MASTER.md "Glass". The PDF page, highlights and the AI provenance surface stay opaque. OS "Reduce transparency" makes glass solid | The owner asked for a glass look via ui-ux-pro-max. "Subtle" was chosen over "vivid" so the paper stays the focus. Surfaces are more opaque than the skill's 15–30% so text keeps ≥ 4.5:1; measured 5.8:1 for the lowest (muted text, dark) |
| D27 | 2026-09-13 | **Amends D25.** Milestones that can run in parallel do so as tracks. Track A stays in the project folder. Each extra track is a sibling clone (`../research-note-mN`) with its own compose project on shifted ports, and its own Claude Code session. Still no git worktrees | The owner wants as much parallel progress as possible. One folder can't hold two checked-out branches, and one stack can't run two branches' E2E suites. A visible sibling folder keeps the code where the owner can see it, unlike a hidden worktree |

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
