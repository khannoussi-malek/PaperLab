# Long documents and large libraries: benchmark

Measured November 2026 on branch `long-docs-ingest` (PR #156). This file records what was tested, how, what won, and the papers behind each decision.

## Summary

PaperLab's search was built for research papers of a few dozen pages. On pharma files of thousands of pages and on libraries of hundreds of papers it broke in three places: ingest was all or nothing, search found passages by meaning only, and one very long passage could push the ingest worker past 5 GB.

| Test | Before | After |
|---|---|---|
| One 10,226-page file, 58 sealed questions | 31 | **48** (+17, −0) |
| Same file, real answers citing the right passage (free cloud models, 60 questions) | 30 | **45** (+15, −0) |
| Same file, real answers with a local 8B model (qwen3:8b, 60 questions) | 28 | 30 (+11, −9) |
| 562 separate papers, 59 sealed questions | 24 | **41** (+17, −0) |
| Workspace search time, 562 papers | 0.03 s (vectors only) | 0.15 s (1.4 s for keywords over every paper) |
| Same, 552,597 chunks across 3,379 papers | | 0.48 s median, 2.77 s slowest |
| Ingest worker peak memory, 10,226-page file | 5.17 GB | **1.33 GB** |

Ingest of the 10,226-page file: about 18 minutes on a quiet machine, back at work 7 to 9 s after a `kill -9` halfway. Word search worked about 2 minutes after upload. A small paper added during the long ingest was ready in 25 to 66 s.

## What changed

1. **Ingest in small steps.** A long paper's text and chunks are saved first, so word search works within minutes. Vectors are made in two-minute slices that resume after a crash; a restarting worker frees what a dead one locked; small papers get turns in between. Uploads go to disk, not memory.
2. **BM25 keyword search** (k1 0.9, b 0.4) computed in SQL over the existing `tsvector`, in place of a sum of word weights.
3. **Hybrid search for long papers.** A paper of 150 chunks or more fuses BM25 and vector rankings by reciprocal rank fusion (k 60).
4. **A character budget, not a fixed 8.** A long paper sends as many passages as fit 24,000 characters, the room a whole short paper gets.
5. **Tables stay whole.** A table's caption and column heads stay in the chunk with its numbers, including tables the detector misses.
6. **Many papers: documents first.** Workspace chat ranks its papers by their 300 nearest chunks (each paper scores the reciprocal ranks of its best 3), then searches the top 10 with BM25 and vectors and fills the same budget.
7. **A 1,024-token limit on embedding.** Only a passage's first 1,024 tokens make its vector; its whole text stays searchable by words and is sent in full.

No migration. Papers already in a library keep their old table chunks until re-indexed.

## How it was tested

### Documents

- **One huge file.** 174 public FDA approval reviews (Drugs@FDA) and EMA assessment reports and product information were downloaded; 70 with a text layer were joined in a seeded random order into one 10,226-page PDF and ingested as one paper (19,852 chunks). No single real file that long was available, so this is a joined file, not one submission. 9 mostly scanned documents (757 pages) were left out.
- **Many papers.** Every regulatory document with a text layer plus 400 research papers from a personal library, each its own paper: 562 papers, 75,554 chunks.
- **Scale.** The 562 papers copied five times: 552,597 chunks across 3,379 papers, for speed only.
- **Earlier rounds.** A 3,024-page file joined from 118 library PDFs, and three regulatory documents of 182 to 844 chunks.

### Questions

- Written by a separate agent that never ran a search or saw a ranking, from pages a seeded script sampled at random.
- 100 questions on the huge file: 35 fact, 35 reworded (avoiding the passage's own words), 22 table numbers, 8 needing two facts.
- Split by seed into 40 for tuning and 60 sealed. Sealed questions were opened once, for methods fixed beforehand.
- The key is exact words from the passage plus the document's page span, so the same sentence in another drug's document doesn't count. A table number and its row label may sit in different chunks, but both must reach the model.

### Scoring

- **Retrieval:** every needed passage reaches the model inside the budget, through the real `retrieve` and `cut_to_budget`.
- **Answers:** the real `chat.prepare` prompt goes to a model, and the answer counts only if a passage it cites holds the fact.

### Pass rules, written before each run

- A change with no new model and no migration must gain at least 2 more questions than it loses, with no document type falling.
- A migration or re-embed of every paper needs +3. A second model needs +3 and under 3 s a question on CPU. A model call per question needs +3, and a failed call must leave search as it was.
- A mix must beat its best part by at least 1.
- Speed: median under 1 s, slowest under 3 s.

## Results by test

### One 10,226-page file, sealed (58 scored)

| Method | Right | Note |
|---|---|---|
| Vectors, top 8 (before) | 31 | |
| Vectors, 24,000-character budget | 41 | |
| **BM25 + vectors, 24,000 characters** | **48** | median 0.40 s, slowest 0.77 s |
| Budget 30,000 | 49 | +1, below the bar |
| BM25 k1 1.5, b 0.75 | 44 | −4 |
| Same with the 1,024-token limit | 48 | +0, −0 |

### Real answers, same file

| Model | Before | After |
|---|---|---|
| Free cloud models via OmniRoute (gemini 3.1 flash-lite, gpt-4o), 60 questions | 30 | 45 |
| Same, sources reordered best first and second best last | | 42 (+2, −5): rejected |
| qwen3:8b on Ollama, 60 questions | 28 (31 given) | 30 (48 given) |
| qwen3:8b, 40 tuning questions, 12,000-character budget | 18 | 20 against 19 at 24,000: rejected |

Median prompt: 2,984 tokens before, 6,593 after. Local median answer: 12 s before, 27 s after, slowest 56 s, never the 120 s limit. On a small local model most of the retrieval gain is lost at the answer step: it often cites a wrong passage among 18 to 33. A larger local model or a cloud model gets the gain.

### 562 papers, sealed (59 scored)

| Method | Right | Median search |
|---|---|---|
| Before: 8 chunks, 3 per paper, vectors | 24 | 0.03 s |
| Before, with the hybrid switch on | 32 | 1.4 s |
| Hybrid with the budget over every paper | 35 | 1.4 s |
| **Documents first, top 10, then hybrid with the budget** | **41** | **0.15 s** |

With five copies present (552,597 chunks), documents first answered 24 of 38 tuning questions against 25 without them; HNSW `ef_search` 200 gets the 25 back at the same speed and is left as a setting for very large libraries.

### Earlier rounds

- 3,024-page file, 33 known questions: vectors top 8 25, branch 31.
- Unseen 60 on three regulatory documents (read several times, so no longer independent): before 38, branch 46.
- Sealed 60 on three documents of up to 336 pages: before 51 (on new chunks), branch 54; HyDE + BM25 + extra terms 55 (+2, −1), below the +3 bar.

### Memory

Peak memory embedding 300 random chunks plus the 120 longest: 5.51 GB at 8,192 tokens, 2.46 GB at 2,048, 1.34 GB at 1,024, 1.02 GB at 512. Turning the ONNX memory arena off made it worse (7.23 GB). 261 of 19,852 chunks run past 1,024 tokens. In the real worker on the 10,226-page file, with the same kill: 5.17 GB became 1.33 GB.

## Why each change: evidence

| Change | Source | What it found | Our test |
|---|---|---|---|
| BM25 | Robertson & Zaragoza 2009 [1] | The origin of BM25 | 31 of 33 against 29 with the old keyword score, nothing lost: the first change to pass |
| k1 0.9, b 0.4 | Lù 2024 [2], Table 3, full text | 41.1 against 39.7 nDCG@10 for 1.5 and 0.75, averaged over 15 BEIR datasets | 1.5 and 0.75 lost 4 sealed questions at 10,226 pages |
| Fusing BM25 and vectors | Cormack et al. 2009 [3] | The origin of reciprocal rank fusion | The mix beat both halves: 31 against 28 (vectors) and 29 (BM25) of 33; 46 against 44 and 43 of 60 |
| Why a mix, why tables | Akarsu et al. 2026 [4], Tables I and IV, full text | Hybrid RRF recall@5 0.695 against 0.644 BM25 and 0.587 dense on 23,088 finance questions; 73% of failures from table structure | Supports both |
| Tables whole | Prompted by [4] | | On 1,265 table numbers in 7 pharma PDFs, those keeping row and column labels went from 41% to 86% |
| Documents first | Liu et al. 2021 [5], Tables 2 and 3, full text | Choosing the document first: top-1 document 28.95 (BM25) to 65.32; top-1 passage 40.08 to 55.37 on NQ | 41 of 59 against 24 across 562 papers, 10 times faster than keywords over every paper |
| Budget, slices, token limit | Our own measurements | | See results above |

## Tested and rejected

| Method | Source | Result |
|---|---|---|
| Convex score fusion | Bruch et al. 2023 [6] | 28 of 33 against 29 (+1, −2) |
| Page score propagation | Zhang et al. 2026, EviProp [7] | 24 of 33 (+1, −6) |
| Cut at the largest score gap | Taguchi et al. 2025, Adaptive-k [8] | 29 against 31 |
| Diversity selection (MMR) | Khan et al. 2026, DF-RAG [9] | no gain |
| Query feedback (Rocchio) | Li et al. 2021 [10] | +1, −1 |
| RM3 expansion, small-to-big vectors, neighbouring chunks, and their mixes | classic methods | best mix 45 of 50 on tuning, then lost 5 known and 3 unseen |
| SPLADE | Lassance & Clinchant 2022 [11] | at most +2, −1; 508 MB model, 3.2 chunks/s |
| ColBERT reranking | Khattab & Zaharia 2020 [12] | +4, −2 on tuning, −2 on known; 2.2 s a question or about 1 GB per 10,000 chunks |
| Small cross-encoder rerankers (bge, MiniLM) | | 0 gain when fused, 1.7 to 3.4 s a question |
| HyDE, alone and with extra terms | Gao et al. 2023 [13] | +2, −1 at best on the sealed set; adds a model call |
| Reordering for "lost in the middle" | Liu et al. 2024 [14] | +2, −5 on real answers |
| Question decomposition | Ammann et al. 2025 [15] | +0, −0 |
| Filter papers by the question's rarest word | Poliakov & Shvai 2024, Multi-Meta-RAG [16] | 23 to 24 of 38 against 25 for documents first |
| Favour the part of the file naming the entity | after [16] | 22 to 25 of 38 against 29 |
| Chunk sizes 800, 1,000, 2,200 | | 41, 40, 38 of 50 against 40 at 1,500 |
| Section titles and numbers in the keyword index | | +2 of 143, needs a migration (+3 bar) |
| Repeating table heads on the next page, caption with rows | | no gain |
| Sending only the best window of a long chunk | | +2, −3 at best |
| Skip-and-fill the budget, dedupe, more candidates, looser per-paper caps | | no gain |
| A larger budget (30,000 to 60,000) | | +1 to +2, below the bar, at 25% to 150% more tokens |
| A 12,000 budget for local models | | +4, −3 against 24,000 |

## Considered, not tested

- Matryoshka truncation of the vectors to 256 or 512 dimensions [17]: a storage gain (about 1.2 MTEB points lost at 256), not a ranking gain.
- Late chunking [18]: about 0 to 2 nDCG points for nomic on short-document benchmarks, and it needs a re-embed.
- Doc2Query-- [19]: gains come from 60-word passages; generating questions for 20,000 chunks costs hours of CPU.
- Filtered HNSW search at scale, ACORN [20]: documents first already keeps the second search to 10 papers.

## Limits

- No single real 10,000-page file: the long file joins 70 real documents of many drugs, which is harder than one drug's submission in one way (similar passages from other drugs) and easier in another (less repetition of one drug's terms).
- Each sealed set was run once. The tuning questions were used to choose what reached them.
- The answer test checks that a cited passage holds the fact, not the prose.
- Local results come from one 8B model.

## References

Checked at Crossref or arXiv in November 2026. "Full text" means the tables cited above were read; the others are cited as the origin of a method or by their abstract.

1. S. Robertson, H. Zaragoza. The Probabilistic Relevance Framework: BM25 and Beyond. Foundations and Trends in Information Retrieval, 2009. https://doi.org/10.1561/1500000019
2. X. H. Lù. BM25S: Orders of magnitude faster lexical search via eager sparse scoring. arXiv 2407.03618, 2024. https://arxiv.org/abs/2407.03618
3. G. V. Cormack, C. L. A. Clarke, S. Büttcher. Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. SIGIR 2009. https://doi.org/10.1145/1571941.1572114
4. Akarsu, Karaman, Mierbach. From BM25 to Corrective RAG: Benchmarking Retrieval Strategies for Text-and-Table Documents. arXiv 2604.01733, 2026. https://arxiv.org/abs/2604.01733
5. Liu et al. Dense Hierarchical Retrieval for Open-domain Question Answering. Findings of EMNLP 2021. https://doi.org/10.18653/v1/2021.findings-emnlp.19
6. S. Bruch, S. Gai, A. Ingber. An Analysis of Fusion Functions for Hybrid Retrieval. ACM TOIS, 2023. https://doi.org/10.1145/3596512
7. Zhang et al. EviProp: Seeded Relevance Diffusion on Chunk-Page Graphs for Long Multimodal Document Retrieval. arXiv 2606.08979, 2026. https://arxiv.org/abs/2606.08979
8. Taguchi et al. Efficient Context Selection for Long-Context QA: No Tuning, No Iteration, Just Adaptive-k. arXiv 2506.08479, 2025. https://arxiv.org/abs/2506.08479
9. Khan et al. DF-RAG: Query-Aware Diversity for Retrieval-Augmented Generation. arXiv 2601.17212, 2026. https://arxiv.org/abs/2601.17212
10. Li et al. Pseudo Relevance Feedback with Deep Language Models and Dense Retrievers: Successes and Pitfalls. arXiv 2108.11044, 2021. https://arxiv.org/abs/2108.11044
11. C. Lassance, S. Clinchant. An Efficiency Study for SPLADE Models. SIGIR 2022. https://arxiv.org/abs/2207.03834
12. O. Khattab, M. Zaharia. ColBERT: Efficient and Effective Passage Search via Contextualized Late Interaction over BERT. SIGIR 2020. https://arxiv.org/abs/2004.12832
13. L. Gao, X. Ma, J. Lin, J. Callan. Precise Zero-Shot Dense Retrieval without Relevance Labels. ACL 2023. https://doi.org/10.18653/v1/2023.acl-long.99
14. Liu et al. Lost in the Middle: How Language Models Use Long Contexts. TACL 2024. https://doi.org/10.1162/tacl_a_00638
15. Ammann et al. Question Decomposition for Retrieval-Augmented Generation. ACL 2025 Student Research Workshop. https://doi.org/10.18653/v1/2025.acl-srw.32
16. Poliakov, Shvai. Multi-Meta-RAG: Improving RAG for Multi-Hop Queries using Database Filtering with LLM-Extracted Metadata. arXiv 2406.13213, 2024. https://arxiv.org/abs/2406.13213
17. Kusupati et al. Matryoshka Representation Learning. NeurIPS 2022. https://arxiv.org/abs/2205.13147
18. Günther et al. Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models. arXiv 2409.04701, 2024. https://arxiv.org/abs/2409.04701
19. Gospodinov et al. Doc2Query--: When Less is More. ECIR 2023. https://doi.org/10.1007/978-3-031-28238-6_31
20. Patel et al. ACORN: Performant and Predicate-Agnostic Search Over Vector Embeddings and Structured Data. SIGMOD 2024. https://arxiv.org/abs/2403.04871
