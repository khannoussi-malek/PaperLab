# PaperLab — paper watch (M7.6) design

Amends the [brief](2026-09-13-paperlab-brief.md) and [addendum 1](2026-09-13-paperlab-brief-addendum-1.md).
Everything there still stands. This adds one capability.

## What it is

A background bot that keeps the user up to date. The user saves a search ("construct
validity in SE surveys"). Once a day the worker asks OpenAlex, arXiv and Semantic
Scholar for papers published since the last check, ranks them against the query and the
user's notes, and puts the best ones in an in-app inbox. The user imports, dismisses, or
follows the DOI link.

The bot **suggests; it never imports**. That keeps the existing rule: references are
never imported without an explicit per-paper user action, and only one hop out.

No LLM is involved. Scores come from embeddings, which are computed rather than
generated text, so nothing here needs a provenance badge.

## Decisions made while brainstorming

| Question | Decision | Rejected |
|---|---|---|
| What defines a topic | An explicit saved search (free-text query) | Category-derived profile; interests inferred from the whole library; follow a paper/author |
| Delivery | In-app inbox with unread count | Email digest (SMTP setup), MCP `whats_new` tool, browser notifications |
| Noise control | Embedding ranking against query + notes, top 20 per watch, rest folded | No ranking; LLM relevance judge; M7.5 library signals (possible later) |
| Sources | OpenAlex + arXiv + Semantic Scholar | OpenAlex only; OpenAlex + arXiv |
| Storage | Reuse `external_refs`; add `watches` + `watch_hits` | A separate `discoveries` table (duplicates refs, `imported_as` drifts); live search with no storage (no unread, no dismiss memory, no background) |
| Placement | M7.6, right after M7.5 | Before M7.5; after M9 |

Why three sources: OpenAlex covers journals and conferences and is already in the stack
(M6.5). arXiv has preprints the day they're posted; OpenAlex picks them up days to weeks
later. Semantic Scholar's `externalIds` returns DOI and arXiv ID together, which is what
lets the merge step recognise the same paper across sources.

## Dependencies

- **M4:** embedding model loaded in the worker, note embeddings.
- **M6.5:** OpenAlex HTTP client (`mailto`, non-fatal handling).
- **M7.5:** `external_refs`, its import job, `imported_as`.

## Data model

```sql
CREATE TABLE watches (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  query            text NOT NULL,
  query_embedding  vector(768),              -- search_query: prefix
  last_checked_at  timestamptz,              -- advanced only when every source succeeded
  last_error       text,                     -- shown in UI; cleared on the next clean run
  created_at       timestamptz DEFAULT now()
);

CREATE TABLE watch_hits (
  watch_id      uuid REFERENCES watches(id) ON DELETE CASCADE,
  ref_id        uuid REFERENCES external_refs(id) ON DELETE CASCADE,
  score         real NOT NULL,
  closest_note  uuid REFERENCES notes(id) ON DELETE SET NULL,
  sources       text[] NOT NULL,             -- subset of {openalex, arxiv, s2}
  status        text NOT NULL DEFAULT 'new' CHECK (status IN ('new','seen','dismissed')),
  found_at      timestamptz DEFAULT now(),
  PRIMARY KEY (watch_id, ref_id)
);

ALTER TABLE external_refs
  ADD COLUMN arxiv_id     text UNIQUE,
  ADD COLUMN s2_id        text UNIQUE,
  ADD COLUMN abstract     text,
  ADD COLUMN published_on date;
-- Also embedding vector(768), unless M7.5 already added it for note-proximity ranking.
```

Choices that aren't obvious, so don't "fix" them:

- **The composite primary key on `watch_hits` is the deduplication.** Every run re-checks a
  7-day overlap window because the APIs index late. `INSERT ... ON CONFLICT DO NOTHING`
  makes the overlap free, and a dismissed hit stays dismissed.
- **"Imported" is not a status.** A hit is imported when `external_refs.imported_as` is
  set, which M7.5 already maintains.
- **One watermark per watch, not per source.** If any source fails, `last_checked_at`
  stays put and the next run repeats the window. The deduplication makes that safe. It's the
  smallest design that never silently skips papers.
- **No edit-query operation.** Changing a query means delete and recreate. Otherwise
  existing hits would carry scores against a query that no longer exists.
- **Deleting a watch keeps its `external_refs` rows.** Other features (M7.5 references
  panel) may point at the same refs.

## Run flow

### Scheduling

- ARQ `cron(run_due_watches, hour=6, minute=0, run_at_startup=True)` in the existing
  worker. `run_at_startup` covers the local-first gap: if the machine was off at 06:00,
  the check happens when the stack next starts.
- `run_due_watches` enqueues one `run_watch(watch_id)` job per watch whose
  `last_checked_at` is NULL or older than 20 hours. One job per watch, so a broken watch
  can't block the others.
- **Check now** in the UI enqueues the same `run_watch` job directly.
- Creating a watch enqueues its first run immediately.

### `run_watch(watch_id)`

Domain logic in `backend/app/core/watches.py` (no fastapi imports). One HTTP adapter per
source in `backend/app/providers/` (`openalex` reused from M6.5, plus `arxiv.py`,
`semantic_scholar.py`), each returning a common candidate shape: IDs (doi, arxiv_id,
openalex_id, s2_id), title, abstract, authors, year, venue, published_on, oa_pdf_url.

```
since = last_checked_at - 7 days            (first run: now - 30 days)

0. embed    the query (search_query: prefix) if query_embedding is NULL
1. fetch    each source in turn, each in its own try/except; collect errors
            openalex  /works?search=<q>&filter=from_publication_date:<since>, mailto,
                      abstract rebuilt from abstract_inverted_index
            arxiv     export.arxiv.org/api/query, sortBy=submittedDate, descending,
                      parsed with stdlib xml.etree; ≥ 3 s between requests
            s2        /graph/v1/paper/search/bulk?query=<q>&publicationDateOrYear=<since>:
                      with x-api-key only if S2_API_KEY is set
2. merge    pure function: candidates sharing any of doi / arxiv_id / openalex_id / s2_id
            become one record; sources[] lists every source that returned it
3. drop     candidates already in the library (papers.doi, papers.openalex_id)
4. upsert   into external_refs, matching on those IDs
5. embed    title + abstract with the search_document: prefix, batched, model loaded
            once at worker startup
6. score    cos(candidate, query_embedding) + NOTE_WEIGHT · max cos(candidate, note)
            closest_note = the argmax note; with no notes, the query term alone
7. insert   watch_hits ON CONFLICT DO NOTHING
8. finish   no errors → last_checked_at = now(), last_error = NULL
            any error → last_checked_at unchanged, last_error = "arxiv: timeout; s2: 429"
```

Constants in `core/watches.py`: `NOTE_WEIGHT = 0.5`, `INBOX_CAP = 20`,
`OVERLAP = 7 days`, `BACKFILL = 30 days`, `DUE_AFTER = 20 hours`. Tune after real use.

Step 6 uses a raw SQL query via `session.execute(text(...))` for the note max-similarity,
binding the vector with `bindparam(..., type_=Vector(768))` (D5).

A preprint and its published version can carry different IDs in different sources and
show up as two hits. Accepted: the merge step matches IDs only, never titles, so it can't
wrongly merge two distinct papers.

### Before writing the M7.6 plan

Spike all three APIs in the scratchpad (roadmap "How we work", step 1) and save real
responses as test fixtures. Confirm:

- OpenAlex `from_publication_date` + `search` combination and paging.
- arXiv free-text → `search_query` translation (quoting, `all:` field, AND of terms).
- Semantic Scholar bulk search date filter and the unauthenticated rate limit.

The endpoint details above describe how the APIs are understood to work. They are not yet
verified against live responses.

## API

Thin routers in `backend/app/api/watches.py`:

| Route | Does |
|---|---|
| `POST /api/watches` `{query}` | Validates non-empty query; stores the watch; enqueues the first run (which embeds the query); returns the watch |
| `GET /api/watches` | Each watch with query, `last_checked_at`, `last_error`, unread count (`status='new'`) |
| `DELETE /api/watches/{id}` | Deletes the watch and its hits |
| `POST /api/watches/{id}/run` | Enqueues `run_watch`; 404 on unknown watch |
| `GET /api/watches/{id}/hits?status=` | Hits joined with `external_refs`, ordered by score desc |
| `PATCH /api/watch-hits/{watch_id}/{ref_id}` `{status}` | `seen` or `dismissed` |

Import uses the M7.5 import endpoint; no new route.

Query embedding at `POST /api/watches` runs in the worker, not the request: the route
stores the watch with `query_embedding` NULL and `run_watch` fills it in first. That keeps
the embedding model out of the API process.

## UI

- **Watches** view in the hash router (D14).
- Create box at the top.
- One section per watch: query, "checked 3h ago" or `last_error` in red, **Check now**,
  delete.
- Hit cards, top `INBOX_CAP` by score, remainder behind "N more":
  - title, authors, year · venue, source badges (OpenAlex / arXiv / S2)
  - abstract, expandable
  - "close to your note: …" when `closest_note` is set; clicking opens the note
  - **Import** when `oa_pdf_url` is set, otherwise the DOI link (manual drop, as in M7.5)
  - **Dismiss**
- Opening a watch's section marks its visible `new` hits as `seen`.
- Total unread badge in the nav, fetched on page load. No polling, no websocket.

## Error handling

- Each source is non-fatal and isolated. One failing source never discards the other
  sources' results for that run.
- Missing `S2_API_KEY` is not an error; S2 runs unauthenticated. A 429 is recorded in
  `last_error` like any other source failure.
- Malformed responses (bad XML, missing fields) are that source's failure, not a crash.
- A candidate with no abstract is still scored on title alone.
- The watermark rule (step 8) guarantees a failed source's papers arrive on the next clean
  run.

## Testing

Per the roadmap testing policy.

- **Unit (pure functions):**
  - merge: overlap on each ID type, three-source merge, disjoint candidates stay separate,
    preprint/published pair with no shared ID stays two records.
  - scoring: with notes (closest note is the argmax), without notes.
- **Providers:** `httpx.MockTransport` serving recorded OpenAlex JSON, arXiv Atom XML and
  S2 JSON, with cases for results, no results, 429, network error and malformed XML.
- **Integration (`run_watch`, real Postgres, fake embedder):**
  - two runs create no duplicate hits
  - a dismissed hit stays dismissed after a rerun
  - one source failing keeps `last_checked_at`, sets `last_error`, still stores the
    other sources' hits
  - a paper already in the library is not a hit
  - `run_due_watches` skips watches checked within 20 hours
- **API:** create / list / run / hits / patch / delete, including 404s and an empty query.
- **E2E (Playwright):** create a watch, see hits (providers stubbed), dismiss one, import one.

## Exit criteria

- A new watch shows ranked hits from at least two sources after one run.
- A second run adds no duplicates.
- With one source's network blocked, the error is visible in the UI, and that source's
  papers appear on the next clean run.
- Importing a hit marks it in-library everywhere it appears.
- `cd backend && uv run pytest --cov` passes the coverage gate; `grep -r fastapi backend/app/core/` prints nothing.

## Out of scope

- Automatic import of any hit.
- Email, push or browser notifications; an MCP `whats_new` tool (cheap to add after M6 if wanted).
- An LLM relevance judge.
- Interests inferred from categories or the whole library.
- Following an author or a paper (M7.5's citing-works direction covers part of this).
- Editing a watch's query.
- Per-watch schedules or per-watch source selection.
- Google Scholar or any HTML scraping.
