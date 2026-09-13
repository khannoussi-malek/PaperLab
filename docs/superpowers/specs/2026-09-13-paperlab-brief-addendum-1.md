# PaperLab — brief addendum 1

This amends [`2026-09-13-paperlab-brief.md`](2026-09-13-paperlab-brief.md). Everything in the original brief still
stands unless contradicted here. Update the plan; don't restart it.

Summary of what changes:

- **New capability:** answering questions that span a whole category of papers,
  which plain top-k retrieval cannot do.
- **New capability:** discovering and importing the papers a paper cites, and the
  papers that cite it.
- **New data:** external topic labels, authors as first-class entities.
- **New graph approach:** community detection over the real graph. Full GraphRAG is
  explicitly rejected — see the rationale, it matters.
- **Confirmed:** no dedicated vector database. Rationale included so it isn't
  revisited.

---

## 1. Why there is no vector database (settled, do not revisit)

The queries this app runs are relational queries with a similarity `ORDER BY`, not
pure nearest-neighbour searches. Splitting the vectors into Qdrant/Pinecone/Chroma
forces one of three bad outcomes:

- **Pre-filter** — pass a large paper-ID list to the vector store on every query.
  Degrades badly when the filter is selective, because HNSW is built for unfiltered
  search.
- **Post-filter** — fetch top-50 and discard non-matching. If a category is 5% of the
  library you keep 2 results out of 50. Silently produces bad retrieval.
- **Duplicate metadata** into the vector store's payload. Now category assignments
  live in two databases and drift with no alert when they disagree.

Also: hybrid retrieval needs BM25, which Postgres has built in (`tsvector`,
`ts_rank`) on the same rows as the vectors. External vector stores have weaker or no
lexical search, so Postgres stays in the request path regardless — the vector store
would be an *additional* system, not a replacement.

Scale is not a factor: ~50k vectors, and latency is dominated by LLM generation.

---

## 2. Global questions — routing, map-reduce, facets

Top-k retrieval answers "where is X mentioned." It cannot answer "what do these
twelve papers collectively assume," because that answer exists in no single chunk.
Three mechanisms, build in this order.

### 2a. Query router

One cheap LLM call before retrieval, classifying the question:

| Type | Example | Handling |
|---|---|---|
| `local` | "what does Smith mean by construct validity" | normal top-k retrieval |
| `per_paper` | "how does each of these measure X" | map-reduce (2b) |
| `global` | "what's the common weakness in this category" | facets (2c) + map-reduce |

Returns `{type, scope: {paper_ids | category_id}}`. Without this the system answers
a global question from eight chunks and sounds confident while being wrong.

### 2b. Map-reduce for per-paper questions

"Compare these twelve papers" is **not** one query over twelve papers. It is twelve
queries over one paper each, plus a synthesis step.

```
map:     for each paper in scope (concurrent, semaphore-limited):
             retrieve 5-6 chunks WITHIN that paper only
             extract a structured answer:
             {paper_id, answer, supporting_chunk_ids, status: found|absent}
reduce:  feed the N structured records to the model for synthesis
```

Two reasons this beats plain retrieval:

- **Every paper gets its turn.** Plain top-8 lets three verbose papers crowd out the
  other nine, and the answer silently omits them.
- **`absent` is a real finding.** "Four of the twelve don't report this at all" is
  often the most interesting result, and no similarity search can surface it —
  absence doesn't match a query vector.

It also fixes the local-model context problem: the reduce step sees twelve short
structured records, not 15k tokens of interleaved excerpts. A 7B model handles the
former and fails at the latter.

Cache map results keyed on `(paper_id, sub_question_hash, prompt_version)` — the same
sub-question over the same paper gives the same answer.

### 2c. Pre-extracted facets

At ingest, extract a fixed set of fields per paper and store them:

```sql
CREATE TABLE paper_facets (
  paper_id        uuid REFERENCES papers(id) ON DELETE CASCADE,
  facet           text NOT NULL,
  value           text,
  evidence_chunks uuid[],
  model           text,
  prompt_version  int,
  PRIMARY KEY (paper_id, facet)
);
```

Facets: `research_question`, `method`, `dataset`, `sample_size`, `key_claim`,
`stated_limitations`, `threats_to_validity`.

This turns "how do these twelve measure X" into a SQL query plus one synthesis call,
instead of twelve retrieval rounds. It also gives you a **comparison table view** per
category — which is what researchers actually want and what no chat interface
provides.

Facets are shown in the UI and are **user-correctable**; corrections persist and are
never overwritten by re-extraction. That auditability is the point.

**Do not design the facet schema up front.** Build this last of the three, after the
app has been used on 30+ real papers. Guessing the schema early produces the wrong
schema.

---

## 3. References and citing works

### 3a. Do not parse the references section

Reference formatting varies by venue, PyMuPDF returns reference text broken across
columns and pages, and GROBID is a heavy JVM dependency. None of it is necessary.

OpenAlex returns the reference list as structured data. Two HTTP calls per paper:

```
GET /works/doi:{doi}
  → referenced_works: [openalex IDs]
  → cited_by_api_url
GET /works?filter=openalex_id:W1|W2|W3&per-page=50
  → titles, authors, years, DOIs, open-access PDF URLs
```

Fallback when there's no DOI: `/works?filter=title.search:...`, then verify year and
first author before trusting the match. Semantic Scholar is a reasonable second
source. All of it stays non-fatal — a paper with no match must remain fully usable.

### 3b. Schema

References you haven't imported are not papers. They have no chunks, no embeddings,
no status machine. Keep them in their own table rather than adding a `stub` flag to
`papers` — otherwise every query on `papers` needs `WHERE status='ready'` forever.

```sql
CREATE TABLE external_refs (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  openalex_id    text UNIQUE,
  doi            text,
  title          text NOT NULL,
  authors        jsonb DEFAULT '[]',
  year           int,
  venue          text,
  oa_pdf_url     text,
  cited_by_count int,
  imported_as    uuid REFERENCES papers(id) ON DELETE SET NULL
);

CREATE TABLE paper_references (
  paper_id  uuid REFERENCES papers(id) ON DELETE CASCADE,
  ref_id    uuid REFERENCES external_refs(id) ON DELETE CASCADE,
  direction text NOT NULL CHECK (direction IN ('cites','cited_by')),
  PRIMARY KEY (paper_id, ref_id, direction)
);
```

`imported_as` is load-bearing: set it once on import and every paper that cited that
reference immediately shows it as in-library. One update resolves N relationships.

### 3c. Ranking — this is what makes the feature useful

A raw list of 40 references is a bibliography; the user already had that in the PDF.
Order by how much *this user* should care:

1. **Co-citation within the library** — `GROUP BY ref_id HAVING count(*) > 1`.
   A reference cited by five of your papers that you don't have is almost certainly
   foundational. Strongest single signal, and it's free.
2. **Proximity to the user's notes** — embed reference titles + abstracts, compare
   against note embeddings.
3. **Open-access availability** — one click to import vs. going hunting. Sort
   actionable ones up.
4. **Citation count** — weak tiebreaker only. Leading with it surfaces famous papers,
   not relevant ones.

The UI reads "12 of these are cited by 3+ papers in your library, 8 have PDFs
available" — a reading list, not a bibliography.

### 3d. Citing works (the reverse direction)

`cited_by_api_url` returns work published *after* this paper. That tells the user
whether a method was later criticised or superseded — which a reference list
structurally cannot. Same UI, filter by year descending. Arguably more valuable than
the forward direction.

### 3e. Import flow

Clicking import on an open-access reference queues a job: fetch `oa_pdf_url`, run the
normal ingestion pipeline, set `imported_as` on reaching `ready`. The only new code is
the fetch — everything downstream is the existing pipeline.

Closed access: show the DOI link, let the user drop the PDF in manually. Do not
attempt paywall workarounds.

Guards:

- **Gate on explicit user action per reference.** Importing 40 papers at once locks
  the worker for an hour.
- **Do not expand transitively.** An imported reference brings its own 40 references;
  two hops out is a thousand stubs. Fetch references only for papers the user
  actually imported, and expand further only on demand.
- OpenAlex wants a `mailto` param and is generous when given one. Batch ID lookups.

---

## 4. Topic labels

Papers carry external labels: author keywords, venue terms, and OpenAlex
`concepts`/`topics` with confidence scores. Free structured metadata.

```sql
CREATE TABLE paper_topics (
  paper_id  uuid REFERENCES papers(id) ON DELETE CASCADE,
  source    text NOT NULL CHECK (source IN ('author','openalex','venue')),
  label     text NOT NULL,
  score     real,
  PRIMARY KEY (paper_id, source, label)
);
```

Keep `source` — author keywords are what the author *claims*, OpenAlex concepts are
what a classifier *inferred*, and the disagreements are informative.

**Keep `paper_topics` strictly separate from `categories`.** Categories are the user's
evolving mental structure; topics are external facts. Merging them means you can no
longer distinguish the user's organisation from someone else's.

Uses: colour the graph by topic, suggest a category on import, surface unimported
references sharing topics with the user's notes, detect that a category has split into
two distinct topic clusters.

---

## 5. Graph strategy — community detection, not GraphRAG

### 5a. Full GraphRAG is rejected

Microsoft-style GraphRAG runs LLM entity-and-relationship extraction over every chunk,
then community detection, then LLM community summaries. Rejected here for four
reasons:

- **Cost.** 30 papers × ~150 chunks = ~4,500 LLM calls, re-run on every corpus change
  or prompt revision. Hours on local Ollama.
- **Small-model weakness.** Entity extraction demands consistent structured output,
  which is precisely what a 7B model is worst at.
- **Entity resolution.** Extraction yields "construct validity", "construct-validity",
  "validity of constructs", and "CV" as four nodes. On an academic corpus this becomes
  the largest single work item in the project.
- **Assumption mismatch.** GraphRAG targets corpora with *no* existing structure —
  news archives, wikis, transcripts. This corpus already has a real citation graph,
  real topic labels, and user notes that explicitly connect papers. Using an LLM to
  hallucinate structure that partly duplicates verified structure is the wrong trade.

An LLM-extracted "relates to" edge is a guess; a citation edge is a fact. In a
research tool, a graph the user can't trust is worse than no graph.

### 5b. What to build instead

Take the useful mechanism from GraphRAG — community detection plus per-community
summaries — and run it on the graph that already exists.

```
nodes:  papers, topics, notes, categories, authors
edges:  cites            (OpenAlex, verified)
        shares_topic     (paper_topics)
        co_anchored      (two papers anchored in the same note)
        same_category    (user's own structure)
        co_authored      (shared author)
```

Zero LLM calls to construct. Run Leiden community detection (`igraph` or `networkx`) —
seconds, not hours. Then **one LLM call per community** to summarise it, using
abstracts and the user's notes in that cluster.

That delivers the global-question capability at roughly 1% of GraphRAG's cost.

```sql
CREATE TABLE communities (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  algo_run_id    uuid NOT NULL,
  member_papers  uuid[],
  member_notes   uuid[],
  summary        text,
  model          text,
  prompt_version int,
  is_stale       boolean DEFAULT false,
  created_at     timestamptz DEFAULT now()
);
```

Recompute when the graph changes materially — a batch of imports, a category
restructure — **not** on every paper import.

### 5c. The one place entity extraction is justified

Extract concepts from the user's **notes only**, never from paper chunks. Notes number
in the low hundreds, not thousands of chunks, so it's tractable even locally. More
importantly, the extracted concepts represent the *user's* thinking rather than an
LLM's reading of papers the user never annotated.

These become concept nodes linking papers, populating the `concept` edge type already
in the schema — with `note_id` recording why the edge exists and `confirmed`
distinguishing derived suggestions from user-approved edges.

---

## 6. Authors as first-class entities

### 6a. Never key authors on names

"J. Smith" / "John Smith" / "John A. Smith" are one person; two different Wei Zhangs
publish in the same subfield. String grouping produces an author view that is wrong in
ways that are hard to notice. OpenAlex `authorships` already provides stable author
IDs, ORCIDs where available, affiliation at time of publication, and position.

```sql
CREATE TABLE authors (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  openalex_id      text UNIQUE,
  orcid            text UNIQUE,
  display_name     text NOT NULL,
  alt_names        text[] DEFAULT '{}',
  last_institution text,
  works_count      int,
  cited_by_count   int,
  h_index          int,
  topics           jsonb DEFAULT '[]',
  fetched_at       timestamptz
);

CREATE TABLE paper_authors (
  paper_id         uuid REFERENCES papers(id) ON DELETE CASCADE,
  author_id        uuid REFERENCES authors(id) ON DELETE CASCADE,
  position         int NOT NULL,
  is_corresponding boolean DEFAULT false,
  institution      text,
  PRIMARY KEY (paper_id, author_id)
);
```

`institution` sits on the join, not the author — people move, and the affiliation as
of that paper is what matters. `position` matters because first and last author carry
different meaning in most fields.

Authors of `external_refs` go in the same table, so "this uncited reference is by
someone who wrote three papers you've already read" works — a strong import signal.

### 6b. Author page — relative to the library, not absolute

An author page showing h-index is a worse Google Scholar. Build the version that only
this app can build:

- Which of their papers are in the library, and which are cited by library papers but
  missing
- Co-authors who also appear in the library (collaboration structure)
- Their topics intersected with the user's categories
- **The user's own notes touching their work** — the real payoff. "Everything I've
  written about X's work" is a question Google Scholar cannot answer.

The co-author graph is a distinct edge type for the graph view. Research communities
often show up more clearly in it than in citation edges.

### 6c. Paper-level metadata to add

From the same OpenAlex response: `type` (article / preprint / chapter),
`is_retracted`, `open_access` status and best OA location, `cited_by_count`,
`referenced_works_count`, `primary_location` (venue + ISSN).

**`is_retracted` gets a prominent banner in the reader.** Reading a retracted paper
unknowingly is a real failure mode and the flag costs nothing.

### 6d. Fetching discipline

Author records need a separate batched fetch — `authorships` gives IDs and names but
not h-index or works count:

```
GET /authors?filter=openalex_id:A1|A2|A3&per-page=50
```

Cache hard: skip refresh for anything with `fetched_at` under 30 days old.

All enrichment stays non-fatal. Preprints, theses, and older papers frequently have no
OpenAlex record. Fall back to PyMuPDF's embedded metadata (usually wrong or empty,
occasionally right), then let the user correct it manually — that escape hatch is
needed regardless.

---

## 7. Revised build order

Steps 1–6 from the original brief are unchanged. From there:

| Step | Work |
|---|---|
| 6.5 | Authors + topics + paper metadata. Slots into the existing `enriching` stage — mostly schema plus one batched fetch. |
| 7 | Graph view: citation edges first, then co-author, then topic. |
| 7.5 | References panel: `external_refs`, ranking, import flow. Citing-works direction. |
| 8 | Hybrid retrieval + reranking, measured against the eval set. |
| 8.5 | Query router, then map-reduce. |
| 9 | Model manager. |
| 10 | Community detection + summaries. |
| 11 | Concept extraction from notes. |
| 12 | Facets — only after 30+ papers have been read in the app. |

Rationale for the tail ordering: community summaries over three papers and eight notes
tell the user nothing. These features need a real corpus to be meaningful, and the
corpus only exists after the app has been used. Building them early means building
them blind and rebuilding them later.

Author pages are read-only views over data gathered at 6.5, so deferring the UI costs
nothing.

---

## 8. Additions to "explicitly out of scope"

Alongside the original exclusions:

- **Full GraphRAG / LLM entity extraction over paper chunks.** See §5a.
- **Parsing the references section from PDF text**, and GROBID. See §3a.
- **Author name-matching or custom disambiguation logic.** Use OpenAlex IDs.
- **Transitive reference expansion.** One hop, on explicit user action only.
- **Merging topics into categories.** They are different things; keep both.
- **A facet schema designed before the app has been used on real papers.**
