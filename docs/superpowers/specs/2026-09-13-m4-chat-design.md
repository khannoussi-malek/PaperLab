# M4 Design: Embeddings, Single-Paper Chat, Promote to Note, Eval Harness

**Status:** approved in brainstorming on 2026-09-13 (UX sections). The backend sections are reviewed with this spec.
**Roadmap:** M4 in [2026-09-13-paperlab-roadmap.md](../plans/2026-09-13-paperlab-roadmap.md). Its scope, exit criteria and Required tests still apply. This spec settles the choices the roadmap leaves open.
**Spike evidence:** `scratchpad/m4-spikes/NOTES.md` (session c758e0ae). Findings are folded in below and marked *(spike)*.

## 1. Product decisions

| # | Decision | Rejected |
|---|---|---|
| U1 | Chat is a **tab** in the reader's right panel: `Notes \| Chat`. The PDF keeps its width. | Third column (PDF too narrow on a laptop); bottom drawer (covers the cited page) |
| U2 | **Select text in an answer → "✦ Save as note"**, mirroring PDF highlighting. | A save button per paragraph; saving the whole answer only |
| U3 | **Saved Q&A, each question independent.** Past Q&As reload with the paper; there are no follow-up turns. | Multi-turn (a rewrite LLM call per turn, harder to evaluate); ephemeral |
| U4 | **The model is set in `.env`** (`LLM_PROVIDER`, `LLM_MODEL`). Each answer shows a read-only `✦ AI · <model> · prompt v<N>` label. The picker arrives in M9. | A picker now (M9 rebuilds it); Ollama only |
| U5 | **Transport: `POST` returning SSE**, read with `fetch` + a stream parser. | `GET` + `EventSource` (question in the URL, auto-reconnect re-runs it); POST then GET (two routes, pending state) |

## 2. User-facing flow

**Chat tab**
- The active tab is kept in the hash route: `#/papers/:id?tab=chat`.
- Past Q&As are listed oldest first, with the input pinned at the bottom. Enter sends, Shift+Enter adds a newline, and input is disabled while an answer is streaming.
- A new question appears immediately, followed by:
  - **Sources**: chips such as `C1 · p.4 · Method`. When retrieval is skipped because the paper is small, one chip reads `Whole paper · N chunks`.
  - **The streamed answer.** Sources always render before the first token.
- `[C1]` in the answer is an inline button. Clicking it, or its chip, scrolls the PDF to the chunk's page and flashes its rects for about 1.5 s.
- An unknown marker (`[C9]`) stays plain text. So do markers in old answers whose chunks were replaced by a re-ingest.
- Each answer has the footer `✦ AI · qwen3:8b · prompt v1`, on the existing opaque AI provenance surface (D26: never glass).

**Errors**
- **Before streaming** (the paper isn't ready, or has no embeddings): an inline alert with the reason; nothing is saved.
- **Mid-stream:** the partial text stays, an inline alert with **Retry** is added, and nothing is saved.
- **Ollama unreachable:** the message is "Can't reach Ollama at `<OLLAMA_URL>`". **Model missing:** "Model `<name>` isn't installed (ollama pull `<name>`)".

**Promote (U2)**
- Selecting text inside a single answer shows a floating **✦ Save as note** button.
- **Anchors** are the chunks whose markers fall inside the selection. If there are none, they're the markers of the paragraph the selection starts in. If still none, the button is disabled with the tooltip "Include a cited passage [C…] to anchor this note".
- **Saving** creates a note with `provenance='llm'` and `source_id` set to the answer's `llm_outputs.id`. The panel switches to **Notes** and scrolls to the new note, which carries the "AI" badge. Editing it flips the badge to "AI · edited" through the existing `edited_provenance`.

## 3. Backend design

### 3.1 Config (`app/config.py`, `.env`)

| Setting | Default | Notes |
|---|---|---|
| `embed_model` | `nomic-ai/nomic-embed-text-v1.5` | *(spike)* The current value has no `nomic-ai/` prefix, and that repo doesn't exist on Hugging Face. |
| `llm_provider` | `ollama` | `ollama` \| `anthropic` \| `fake` |
| `llm_model` | `qwen3:8b` | |
| `ollama_url` | `http://host.docker.internal:11434` | Missing from `.env` today *(spike)* |
| `anthropic_api_key` | `None` | Required only when `llm_provider=anthropic`; checked at startup |

### 3.2 Dependencies and image
- **`torch`** becomes a direct dependency pinned to the PyTorch CPU index through `[tool.uv.sources]`. *(spike)* Otherwise the Linux image pulls about 43 CUDA wheels, several GB.
- **`sentence-transformers`** is loaded **without** `trust_remote_code`. *(spike)* With the pinned transformers 5.17, remote code crashes on `encode`, while the built-in NomicBert gives identical vectors.
- **`anthropic`** is added as a normal dependency; one adapter doesn't justify an extras group.

### 3.3 Migration `0003_chat_outputs`
- `llm_outputs` gains:
  - `question text`: NULL for kinds other than chat.
  - `source_chunks uuid[] NOT NULL DEFAULT '{}'`: the ordered chunk ids behind `C1…Cn`, so `C{i}` = `source_chunks[i-1]`.
- `cited_chunks` keeps its meaning: the subset actually cited in the final text.
- There's no FK on array elements. When re-ingest deletes a chunk, its marker renders as plain text (§2).
- **Collision rule (D27):** track B is also adding `0003`. Whichever branch merges second renumbers its revision and `down_revision`.

### 3.4 Embedding stage (worker)
- **New module `app/providers/embedding.py`:**
  - `load()` returns a `SentenceTransformer`.
  - `embed_documents(model, texts)` prefixes each text with `search_document: `.
  - `embed_query(model, text)` prefixes with `search_query: `.
  - Both pass `normalize_embeddings=True` *(spike: vectors aren't normalized by default)* and run under `asyncio.to_thread`.
- **Loaded once:** `WorkerSettings.on_startup` loads the model into `ctx["embedder"]`, and `ingest_paper` uses `ctx["embedder"]`.
- **Batch size** is 16, to keep peak memory well inside the 7.65 GiB Docker VM *(spike: 1.2–2.2 GB peak)*.
- **Status flow:** `chunking → embedding → ready`. `replace_chunks` already replaces rows, and embeddings are written onto the new rows (`UPDATE chunks SET embedding = …` in one statement via `unnest`). A re-ingest therefore replaces the vectors.
- **Failures:** an embedder failure lands in the existing `except` and ends in `failed` with `status_error`.
- **Speed:** about 7 chunks/s in a Linux container *(spike)*, so a 60-page paper spends about a minute in `embedding`. The library already shows the stage.
- **Papers that are `ready` but have no embeddings** (ingested before M4): the chat route answers 409, and the UI offers "Re-index" by calling the existing `POST /api/papers/{id}/reingest`.

### 3.5 Query embedding (API)
- The API process loads the same model **lazily on the first chat request**, with a module-level cache in `providers/embedding.py`, and reuses it afterwards.
- **Memory:** that's a second copy of the model, about 0.6–1.2 GB at batch size 1.
- **Why not a queue:** routing queries through ARQ would add latency and moving parts, and Ollama's `nomic-embed-text` is a different quantization, so its vectors wouldn't match.
- **Ceiling:** `ponytail:` two model copies. Move query embedding into a shared service only if memory becomes a real problem.

### 3.6 `app/core/retrieval.py`
- **Signature:** `retrieve(session, query: str, *, paper_ids: list[UUID] | None = None, k: int = 8, embedder=None) -> list[RetrievedChunk]`.
  - `RetrievedChunk` has id, paper_id, page, section, bbox, text and distance.
  - `embedder=None` means the process-cached model from §3.5; tests pass a fake.
  - `category_id` arrives in M5 as a keyword argument, so no caller breaks.
- **Query:** raw SQL `ORDER BY embedding <=> :q LIMIT :k`, with `bindparam("q", type_=Vector(768))` (D5) and `paper_id = ANY(:ids)` when a scope is given. Rows with a NULL `embedding` are excluded.
- **M5 caveat, recorded as a known issue:** HNSW with a filter can silently drop rows *(spike: forced plan returned 0/8)*. Before M5 ships multi-paper scopes, add `SET LOCAL hnsw.iterative_scan = relaxed_order`. M4 isn't affected: at the current size the planner does an exact scan.

### 3.7 LLM providers
- **`app/providers/base.py`:** a `Protocol LLM` with a `model: str` attribute and `stream(system: str, prompt: str) -> AsyncIterator[str]`. It raises `LLMUnavailable(message)` for connection or missing-model problems, and `LLMError(message)` for anything else.
- **`app/providers/llm.py`:**
  - **`OllamaLLM`:**
    - Streams `httpx` NDJSON from `/api/chat` with `stream: true, think: false` *(spike: thinking models otherwise stream empty content first)*.
    - Timeout: connect 5 s, read 120 s *(spike: cold load 7–10 s)*.
    - A 404 raises `LLMUnavailable("Model … isn't installed")`, and a `ConnectError` raises `LLMUnavailable("Can't reach Ollama at …")`.
    - An `{"error":…}` line in the stream raises `LLMError`.
  - **`AnthropicLLM`:** `client.messages.stream(...)`, yielding `text_stream`. SDK errors map to `LLMError`. *(spike)* A mid-stream overload arrives as `APIStatusError` with status 200, so catch the base class.
  - **`FakeLLM`:** deterministic. It yields a canned answer word by word, citing `[C1]` and splitting the marker across tokens (`"[C"`, `"1]"`). It records every call on the instance, so tests can assert what was sent. `LLM_PROVIDER=fake` selects it, which is also how the E2E stack runs chat.
  - **`get_llm()`** builds the configured provider once per process.
- **Test fakes at the HTTP edge:** `httpx.MockTransport` for Ollama. The Anthropic SDK 1.x runs on `httpx2`, so its adapter tests use `httpx2.MockTransport` *(spike: this corrects the roadmap's wording)*.

### 3.8 Prompts
- `backend/prompts/chat.v1.md` holds the system prompt and the context template.
- `app/core/prompts.py`: `load(name, version) -> str` raises `FileNotFoundError` naming the missing `<name>.v<N>.md`. `CHAT_PROMPT_VERSION = 1` lives next to the chat service.
- **Context block per source:** `[C1] (Devlin 2019, p.4, Method)\n<chunk text>`.
  - Author and year come from `papers.authors` / `papers.year` when set, otherwise the paper title.
  - The section is omitted when it's NULL.

### 3.9 `app/core/chat.py`
- **`SMALL_PAPER_CHARS = 24_000`.** `ponytail:` a character count stands in for tokens. Revisit with the eval numbers or a model's real context size.
- **`prepare(session, paper_id, question, embedder) -> Prepared`:** returns `(sources, system, prompt, whole_paper)`.
  - If the paper's total chunk text is ≤ `SMALL_PAPER_CHARS`, all chunks are sent in reading order and retrieval is skipped.
  - Otherwise it calls `retrieve(..., paper_ids=[paper_id], k=8)`.
- **`parse_citations(text, n) -> list[int]`:** a regex over the final text returning the valid source indexes in first-seen order. The backend only needs the final text; the incremental parser lives in the frontend *(spike)*.
- **`save_answer(session, paper_id, question, prepared, content, model) -> uuid`:** writes `llm_outputs(kind='chat', question, content, source_chunks, cited_chunks, model, prompt_version)`. Chat never touches `notes`.
- **`list_answers(session, paper_id)`:** returns history rows, each with its sources resolved to chunks. Deleted chunks come back as `null`.

### 3.10 API (`app/api/chat.py`)
- **`POST /api/papers/{paper_id}/chat`** with body `{question: str (1..2000 chars, stripped)}` and `response_class=EventSourceResponse` *(spike: FastAPI 0.141.1)*.
  - **Checked in a dependency, before streaming** *(spike: an exception raised inside the generator only drops the connection)*:
    - unknown paper → 404
    - paper not `ready` → 409 `paper_not_ready`
    - no embedded chunks and not small → 409 `paper_not_indexed`
    - bad body → 422
  - **Transaction:** the generator runs `prepare` and **ends the transaction before calling the LLM** *(spike: otherwise the request session stays open for the whole stream)*. The answer is saved in a fresh session after the last token.
  - **Events:**
    - `sources`: `{whole_paper: bool, sources: [{label: "C1", chunk_id, page, section, bbox}]}`.
    - `token`: `{text}`, repeated.
    - `done`: `{output_id, model, prompt_version, cited: ["C1", ...]}`.
    - `error`: `{message, retryable: bool}`. It replaces `done` whenever `LLMUnavailable`, `LLMError` or a save failure happens after `sources`, and nothing is saved.
- **`GET /api/papers/{paper_id}/chat`:** the saved Q&A list, oldest first. 404 for an unknown paper.
- **`POST /api/notes/promote`** with body `{output_id, body, chunk_ids: [uuid, ...] (min 1)}`. It calls the new `notes.promote_llm_fragment` in `core/notes.py`, which is the only place provenance rules live.
  - unknown output → 404
  - blank body → 422
  - normalized body is not a substring of the output's content → 422 `body_not_in_output`. This guard stops text you wrote from being labelled as AI output.
  - any `chunk_id` not in the output's `source_chunks`, or the chunk no longer exists → 422
  - **On success:** one anchor per chunk (page, bbox and quoted text from the chunk, `chunk_id` left NULL per D10), `provenance='llm'`, `source_id=output_id`.

## 4. Frontend design (D24 rules apply)
- **`features/reader/RightPanel.tsx`:** shadcn `Tabs` wrapping the existing `NotesPanel` and the new `ChatPanel`. `route.ts` gains the `tab` param.
- **`features/chat/sse.ts`:** a pure parser from `Uint8Array` chunks to `{event, data}` records. It handles events split across chunks and multi-line `data:`.
- **`features/chat/citations.ts`:** a pure incremental splitter from a token stream to segments, `text | cite(label)`. It holds back a partial `[`, `[C` or `[C12` until it resolves, and leaves unknown labels as text *(spike prototype: 11 cases, including Ollama's real `" [", "C", "1", "]["` split)*.
- **`features/chat/useChatStream.ts`:** `fetch` + `sse.ts`. The state goes `idle → sources → streaming → done | error`. On `done` it invalidates the chat history query.
- **`features/chat/promote.ts`:** a pure function mapping a DOM selection inside an answer (segment offsets) to `{body, chunk_ids}`, using the selection → paragraph → none fallback from §2.
- **`api/queries.ts`** gains `useChatHistory(paperId)` and `usePromoteNote()`. The promote mutation invalidates the notes query.
- **Reader:** a `flashChunk(page, rects)` built on the existing scroll-to-note path, so there's no second scroll implementation.

## 5. Eval harness
- **`backend/evals/questions.yaml`:** 20 questions over the two arXiv papers used in M2. Each entry names `paper` (by filename), `question`, and `expected: [{page, contains: "<distinctive phrase>"}]`.
- **`backend/evals/run.py`:** embeds each question, calls `retrieve(k=…)`, and prints recall@k for k ∈ {4, 8}. A hit means any retrieved chunk is on an expected page and contains its phrase (normalized).
  - It works on any DB URL and exits non-zero on a malformed file.
  - The test suite runs `run.py` on a 2-question seeded fixture with a fake embedder.
- **Baseline:** the real number is recorded in the roadmap. K2 (heading false positives) and K3 (references chunks) are decided from these numbers: keep, exclude or down-weight, each with a D-entry.

## 6. Testing (maps to roadmap M4 Required tests)
- **Worker** (fake embedder recording inputs, via `ingest_paper`):
  - the `search_document:` prefix
  - the model loads once per worker (`on_startup`)
  - a re-ingest replaces the vectors
  - an embedder failure ends in `failed` with `status_error`
- **Providers:**
  - `embed_query` uses `search_query:` and normalizes.
  - `OllamaLLM` via `httpx.MockTransport`: stream, final done line, 404 missing model, connect error, in-stream error line.
  - `AnthropicLLM` via `httpx2.MockTransport`: text stream, and an overload arriving as `APIStatusError` with status 200.
- **`retrieve`:** on seeded vectors it returns the true top k in order, respects `paper_ids`, and skips chunks that have no embedding.
- **Chat core:**
  - the small-paper skip sends all chunks
  - context formatting
  - prompt loader (by name and version; a missing version raises)
  - `parse_citations` (repeats, unknown `C9`)
  - `save_answer` fills every column
  - chat inserts no notes
- **Chat API, with `FakeLLM`:**
  - events arrive as `sources → token… → done`
  - one `llm_outputs` row is written
  - an `LLMError` mid-stream gives an `error` event and no row
  - 404 unknown paper; 409 not ready; 409 not indexed; 422 bad body
  - history ordering
- **Promote:**
  - `provenance='llm'` with `source_id` and anchors from chunks
  - editing gives `llm_edited`
  - 404 unknown output
  - 422 for a blank body, a body not found in the output, a foreign chunk and a deleted chunk
- **Vitest:** `sse.test.ts`, `citations.test.ts` (including the Ollama split), `promote.test.ts` (selection, paragraph fallback, none), and `route.test.ts` for the tab param.
- **Playwright** (stack with `LLM_PROVIDER=fake`, `paperId` fixture):
  - sources render before the answer
  - clicking `[C1]` scrolls to the page and flashes the rect
  - promoting a selection shows the "AI" badge, and an edit shows "AI · edited"
  - history survives a reload
- **Deliberate-bug checks** per D23 wherever red-first is impossible, as in M3.
- **Done means** all suites are green in one run (roadmap test requirement 7), plus the recall@k baseline recorded.

## 7. Out of scope for M4
Multi-turn chat, the model picker (M9), category or multi-paper scopes and the diversity cap (M5), hybrid retrieval and reranking (M8), streaming token counts or cost display, cancelling a stream mid-answer, and answer regeneration (ask again instead).
