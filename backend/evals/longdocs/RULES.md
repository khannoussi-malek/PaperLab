# Rules log

This is the benchmark's working log, unedited except that "the owner" now reads "the author". Each rule was written into it before the run it governs, and the results that followed come after it.

The log was kept in the author's local notes, not in version control. Its order shows when each rule was written relative to its results, but no commit timestamp can prove it. The code each run measured is in these PaperLab commits:
- `3eb81ce`: the 1,024-token embedding limit.
- `0d699e0`: documents-first workspace search.
- `2d422eb` and `19d5da8`: help text and documentation.

Earlier rounds ran on the branch before these commits; the scripts in `scripts/` patch the same code paths.

---

# Long documents: testing every idea and mix (rules written 2026-11-05, before any run)

Corpus: the 3,024-page fixture with the final chunker (tables kept together). Questions: the 33 fixed questions.

Baseline: hybrid with the 24,000-character budget, as on the branch.

Score: questions whose needed passages all reach the model, under the same 24,000-character budget. Also reported: top 8, and each drug separately.

## Pass rules

1. An idea or mix with no new model must gain at least 2 questions over the baseline, and lose ground on neither drug.
2. An idea that needs a second model download must gain at least 3, for the same reason, and answer in under 3 seconds on this Mac's CPU.
3. A mix must beat its best single part by at least 1 question. Otherwise the simpler part wins.

## What this cannot show

The questions and answer key were seen before these runs, and 33 is few. Any winner must be confirmed on a real long pharma file with a key written first. A win here is a candidate, not a proof.

## Round 1 results (known 33 questions, tables-together chunks)

```
BASELINE hybrid                                      budget 29  (apixaban 12, semaglutide 17)  top8 28
vector only                                          budget 28  (apixaban 11, semaglutide 17)  top8 26
keyword only                                         budget 26  (apixaban 13, semaglutide 13)  top8 27
hybrid, 100 candidates (retrieval.py:22)             budget 29  (apixaban 12, semaglutide 17)  top8 28
hybrid, 200 candidates                               budget 29  (apixaban 12, semaglutide 17)  top8 28
hybrid, duplicates removed                           budget 30  (apixaban 12, semaglutide 18)  top8 29
page first, then chunks                              budget 28  (apixaban 11, semaglutide 17)  top8 27
page first, duplicates removed                       budget 29  (apixaban 11, semaglutide 18)  top8 29
section first, then chunks                           budget 29  (apixaban 12, semaglutide 17)  top8 28
search small, send large: vectors                    budget 28  (apixaban 12, semaglutide 16)  top8 27
search small, send large: hybrid                     budget 30  (apixaban 12, semaglutide 18)  top8 28
small + normal vectors + keywords                    budget 30  (apixaban 12, semaglutide 18)  top8 27
small + normal + keywords, 100 candidates, deduped   budget 30  (apixaban 12, semaglutide 18)  top8 29
bge reranker over hybrid top 40                      budget 28  (apixaban 12, semaglutide 16)  top8 26
reranker seconds a question, 40 pairs: median 3.44 max 4.13
bge reranker fused with hybrid                       budget 30  (apixaban 12, semaglutide 18)  top8 27
bge reranker over hybrid 100, deduped                budget 26  (apixaban 10, semaglutide 16)  top8 24
bge reranker over small+normal+keywords 100          budget 27  (apixaban 11, semaglutide 16)  top8 24
reranker fused with small+normal+keywords            budget 30  (apixaban 12, semaglutide 18)  top8 28
BASELINE hybrid                              gained [] lost []
vector only                                  gained ['q03emaglutide'] lost ['q02– apixaban', 'q09emaglutide']
keyword only                                 gained ['q18– apixaban'] lost ['q05emaglutide', 'q09emaglutide', 'q11emaglutide', 'q1
hybrid, 100 candidates (retrieval.py:22)     gained [] lost []
hybrid, 200 candidates                       gained [] lost []
hybrid, duplicates removed                   gained ['q03emaglutide'] lost []
page first, then chunks                      gained [] lost ['q03– apixaban']
page first, duplicates removed               gained ['q03emaglutide'] lost ['q03– apixaban']
section first, then chunks                   gained [] lost []
search small, send large: vectors            gained ['q03emaglutide'] lost ['q02emaglutide', 'q10emaglutide']
search small, send large: hybrid             gained ['q03emaglutide'] lost []
small + normal vectors + keywords            gained ['q03emaglutide'] lost []
small + normal + keywords, 100 candidates, d gained ['q03emaglutide'] lost []
bge reranker over hybrid top 40              gained ['q03emaglutide'] lost ['q02emaglutide', 'q09emaglutide']
bge reranker fused with hybrid               gained ['q03emaglutide'] lost []
bge reranker over hybrid 100, deduped        gained ['q03emaglutide'] lost ['q02emaglutide', 'q02– apixaban', 'q04– apixaban', 'q0
bge reranker over small+normal+keywords 100  gained ['q03emaglutide'] lost ['q02emaglutide', 'q04– apixaban', 'q09emaglutide']
reranker fused with small+normal+keywords    gained ['q03emaglutide'] lost []
```

No candidate meets rule 1 (+2). Every +1 is the same question (semaglutide q03). The reranker fails rule 2 twice: no gain of 3, and 3.4 s a question. Finalists for the held-out questions, kept despite missing the bar and said so here: duplicates removed, and search small plus keywords. They cost little and lost nothing.

Playwright, first run under load (2026-11-05): 52 passed, 4 chat specs failed on timing; all 4 pass alone. Full clean run still due on the final code. That run OOM-killed the live ingest worker's process once (it restarted, no papers lost) and my throwaway database, which was set to die first. Run Playwright only with agents and throwaway databases idle.

## Round 2 results (known 33 questions, final chunks)

```
BASELINE hybrid (app keyword score, RRF)           29 apx 12 sem 17 top8 28 sent 11/22843  +[] -[] 
hybrid, duplicates removed                         30 apx 12 sem 18 top8 29 sent 10/23027  +['semq03'] -[] 
convex fusion, alpha 0.5                           28 apx 13 sem 15 top8 26 sent  9/22928  +['apiq18'] -['semq09', 'semq12'] 
convex fusion, tuned on the other drug             28 apx 13 sem 15 top8 28 sent  9/22989  +['apiq18'] -['semq09', 'semq12'] tuned {'apixaban': 0.3, 'semaglutide': 0.5}
BM25 alone k1 1.5 b .75                            29 apx 12 sem 17 top8 26 sent 14/22987  +['apiq18', 'semq03'] -['apiq04', 'semq09'] 
BM25 alone k1 .9 b .4                              29 apx 12 sem 17 top8 27 sent 10/23129  +['apiq18', 'semq03'] -['apiq04', 'semq09'] 
RRF vectors + BM25 k1 .9 b .4                      31 apx 13 sem 18 top8 27 sent 11/22715  +['apiq18', 'semq03'] -[] 
RRF + BM25, numbers kept whole                     31 apx 13 sem 18 top8 27 sent 11/22670  +['apiq18', 'semq03'] -[] 
RRF + BM25, numbers, headings x2                   31 apx 13 sem 18 top8 27 sent 12/22679  +['apiq18', 'semq03'] -[] 
RRF + BM25, running heads removed                  31 apx 13 sem 18 top8 28 sent 11/23063  +['apiq18', 'semq03'] -[] 
convex + BM25 numbers headings, alpha .5           30 apx 13 sem 17 top8 28 sent 10/22673  +['apiq18', 'semq03'] -['semq09'] 
convex + BM25 numbers headings, tuned              30 apx 13 sem 17 top8 28 sent 10/22673  +['apiq18', 'semq03'] -['semq09'] tuned {'apixaban': 0.5, 'semaglutide': 0.5}
RRF + BM25 k1 b tuned on the other drug            31 apx 13 sem 18 top8 28 sent 11/22670  +['apiq18', 'semq03'] -[] {'apixaban': (0.6, 0.2), 'semaglutide': (0.6, 0.2)}
question type: numeric leans on keywords           31 apx 13 sem 18 top8 29 sent 11/22870  +['apiq18', 'semq03'] -[] 
question type, RRF weights 1 : 2                   31 apx 13 sem 18 top8 29 sent 11/22943  +['apiq18', 'semq03'] -[] 
per-list k: 20 for keywords, 60 for vectors        30 apx 13 sem 17 top8 28 sent 10/22946  +['apiq18', 'semq03'] -['semq09'] 
page score propagation                             24 apx 12 sem 12 top8 19 sent 13/22410  +['semq03'] -['semq01', 'semq06', 'semq07', 'semq12', 'semq13', 'semq17'] 
MMR lambda .9                                      31 apx 13 sem 18 top8 27 sent 12/22655  +['apiq18', 'semq03'] -[] 
MMR lambda .8                                      31 apx 13 sem 18 top8 28 sent 12/22715  +['apiq18', 'semq03'] -[] 
query feedback, keeping the question at .7         29 apx 12 sem 17 top8 27 sent 11/22671  +['semq03'] -['semq05'] 
MIX BM25 numbers headings + dedupe                 29 apx 12 sem 17 top8 28 sent 11/22647  +['semq03'] -['semq09'] 
MIX + propagation                                  26 apx 12 sem 14 top8 19 sent 13/22567  +['semq03'] -['semq06', 'semq07', 'semq12', 'semq13'] 
MIX + MMR .9                                       31 apx 13 sem 18 top8 29 sent 12/22595  +['apiq18', 'semq03'] -[] 
MIX + feedback                                     31 apx 13 sem 18 top8 29 sent 11/22631  +['apiq18', 'semq03'] -[] 
MIX with adaptive cut at the largest gap           29 apx 12 sem 17 top8 28 sent 10/22631  +['semq03'] -['semq09'] 
```

First to pass rule 1: real BM25 (k1 .9, b .4) in place of the sum-of-IDF keyword score: 31, gain 2, nothing lost, both drugs up. Convex fusion, the research agent's first pick, lost 2 and gained 1. Page propagation lost 6. Mixes did not beat BM25 alone, so rule 3 keeps the simpler one. Finalists for the unseen questions: BM25 plus vectors; with numbers and headings; with question type; with dedupe; with MMR.

## Round 3 rules (written 2026-11-05, before any run on the development set)

Questions: 50 new ones on three new documents (Brilinta medical review, Ozempic EU label, EHRA NOAC guide), written with no search run. These choose finalists, so failures here may be read. The 33 known questions stay a filter; the unseen 60 stay a final check, once a round, totals only.

Baseline: vectors + real BM25, RRF, 24,000 characters: the code as committed.

1. No new model: gain at least 2 of 50 over the baseline, lose ground on no document.
2. A second model: gain at least 3 and answer in under 3 seconds a question on this Mac's CPU.
3. A migration or a re-embed of every paper: gain at least 3, because existing users pay for it once.
4. A mix must beat its best part by at least 1.
5. The finalists must also hold on the known 33 (no loss) before they reach the unseen 60.

## Round 3, first results (development set)

Real code against the simulation: known 31 of 33 answerable (same as the simulation); dev 38 with the 1,000-chunk rule removed (simulation 37; the app counts distinct words for chunk length). Keyword half at 51,840 chunks in one paper: median 0.22 s, p90 0.94 s; before BM25 0.45 s, p90 0.78 s.

The 1,000-chunk rule costs 5 of 50: real code 33 with it, 38 without it, on documents of 182 to 844 chunks.

Vectors 33; B 37; numbers 39; headings 40; numbers + headings 40; RM3 40; small vectors 41 (+4 -0); heading in the vector 39; neighbours 38 (tables +2, -1). No method answers q02, q15, q19, q29 (needed chunk at vector rank 240, 125, 170, 31). q26 and q27 fail because the table's title is in a different chunk from its numbers: a chunking bug.

Chunker fix (2026-11-05): the size limit often fell between a table's column heads and its numbers, and find_tables missed many tables. Caption and heads now move with the first row. Baseline on the development set 37 -> 40, tables 11 -> 12. New baseline 40. With it: RM3 41, numbers + headings 41, RM3 + neighbours of the top result 42, small + RM3 44, small + RM3 + neighbours of the top result 45.

Short papers (Attention, BERT; 20 repo questions), hybrid against vectors alone: 20 and 20 at 24,000 characters, 20 and 20 at 12,000, 17 and 20 at 6,000. LONG_PAPER_CHUNKS lowered from 1,000 to 150: all short-paper results stay vector-only.

## Round 3 finalists on the known and unseen questions (fixed chunks)

```
known 33 answerable (B 31)   vectors 28; numbers+headings 31 (-0); RM3 30; small 30; small+RM3 27; small+RM3+neighbours 26; RM3+neighbours 30; neighbours 29; small+neighbours 28
unseen 60 (B 46)             vectors 42; numbers+headings 49 (+3 -0); RM3 46; small 44; small+RM3 47; small+RM3+neighbours 46; RM3+neighbours 48 (+3 -1); neighbours 47; small+neighbours 45
```

The development winner failed: small + RM3 + neighbours was 45 of 50 there, but lost 5 known questions and 3 unseen ones. Small vectors fail rule 3 and rule 5 and will not be built. Only numbers + headings loses nothing on any set.

## Numbers + headings in the real code: fails rule 3 (2026-11-05)

Migration 0067 (section title in tsv, thousands commas removed) built and run on the throwaway database only; 27,855 chunks took 11 s.

```
real code     dev 50   known 33   unseen 60
no migration    40       31          46
migration       41       31          47
```

+2 of 143, nothing lost; rule 3 asks for +3. The simulation's 49 did not carry over: it also counted every number twice. Giving numbers double weight in the real SQL changed no total, so that went too. Reverted; not shipped. The unseen set has now been read several times this round, so its numbers are no longer independent: a new unseen set gives the final figure.

## Second models on the fixed chunks: all fail rule 2 (2026-11-05)

SPLADE, on old chunks: at most +2 -1 over B, 508 MB, 3.2 chunks/s. Small reranker (MiniLM-L-12): 0 over B when fused, +3 -1 alone, 1.7 s a question. ColBERT small over the top 50 of B, fixed chunks: dev 42 (+4 -2), known 29 (-2); fused dev 40, known 30. 128 MB; 2.2 s a question to encode at query time, or roughly a gigabyte per 10,000 chunks to store. No second model.

First HyDE/term run was unfair: the free model's hidden reasoning used up 300 tokens, leaving a median 50-character passage. Rerun at 1,500.

## Question rewrites (HyDE and term expansion), free model, 1,500 tokens

```
                         dev 50 (B 40)   known 33 (B 31)   unseen 60 (B 46)
HyDE vector + BM25       42 (+3 -1)      32 (+1 -0)        45 (+1 -2)
terms in BM25            43 (+4 -1)      29 (+0 -2)        43 (+2 -5)
HyDE vector + terms      44 (+6 -2)      31 (+0 -0)        45 (+4 -5)
HyDE + BM25 + terms      44 (+6 -2)      32 (+1 -0)        48 (+4 -2)
```

Six unseen questions had no rewrite (model unavailable) and fell back.

Rule for this method, written after these results and before the sealed final set is opened: it ships only if, on the final 60, it nets at least +3 over the same search without rewrites and loses no document, and only if a failed or slow model call leaves the search exactly as it is without rewrites. Both versions run once on the final set. The first score there is the number reported.

Round 4: chunk size (800: 41, 1,000: 40, 1,500: 40, 2,200: 38 of 50) and repeating a table's heads on its next page (dev 40, known 30): neither gains.

Final set: 60 new questions, 3 new documents, written with no search run. Methods fixed before opening: vectors top 8 (the old way, on fixed chunks), vectors at the budget, B, B + HyDE, B + HyDE + terms. One run.

## Final set, one run (2026-11-05)

```
A vectors top 8 (fixed chunks)  51  fact 13 multi 2 reworded 21 table 15
vectors at the budget           52
B committed, real retrieve      54  fact 15 multi 2 reworded 22 table 15   (the simulation also says 54)
B + HyDE                        53  (+0 -1)
B + HyDE + terms                55  (+2 -1), fails the +3 rule
```

The loop stops on rule 2: 90%. Winner: B. Caveat: this set is easier than the earlier unseen one (the old way scores 85% here, 63% there), and its longest document has 336 pages, because FDA blocked further downloads. The 3,024-page fixture and the 677-page FDA review remain the evidence at length.

## Answer test, free cloud model (33 fixed questions on the 3,024-page fixture, final chunks and code)

A old (vectors, top 8) 25 right, 25 given. B branch 30 right, 31 given. C branch in document order 30 right, 31 given.
C gained apixaban q04, lost semaglutide q11: fails "C beats B by 2 or more and loses at most 1". Sources stay in ranked order.
Median answer 3.1 s; prompt 4,068 tokens (A), 5,848 (B). Models: gpt-4o 87, gemini 3.5-flash 12, gpt-4o-mini 1.
Checked: stored fixture, dev and old-unseen chunks equal what the branch's chunker makes today, exact text.

## Local model rule, written before the run

Same 33 questions, real OllamaLLM (num_ctx 16,384, think off), qwen3:8b, one question at a time, model cold before the first.
A old, B branch (24,000 characters), E branch at 15,000 characters.
- A smaller budget for local models ships only if E is right at least as often as B and either its median answer is 25% faster or B hit the 120 s limit at least once. Otherwise one budget for every model stays.
- If B is not right at least as often as A locally, say so plainly: the branch's gain is then cloud only.

Local run note: after 48 answers the disk hit 0 (Ollama's 7.4 GB model pushed swap to 13 GB on a disk with 11 GB free), which stopped Docker Desktop and the live stack. The run now stops itself under 5 GB free. E's 0.3 s first token in those 48 answers is Ollama's prompt cache, as E's prompt starts like B's and ran right after it; the remaining questions run B, A, E, and only those give E a fair time.

Local run, partial and final for now: 16 of 33 questions before the disk filled; the Mac then restarted and wiped the scratch folder and throwaway database. qwen3:8b: A 9, B 14, E 11 right. E vs B: +0 -3. Median whole answer A 15.8 s, B 21.9 s; no answer hit the 120 s limit (slowest 32.1 s). E's time is not comparable (prompt cache). The rerun needs the fixture and database rebuilt, and more free disk.

## Round 5: true length (rules written 2026-11-05, before any search on these documents)

Why: the sealed set's longest document was 336 pages; the author's case is up to 10,000. B is the method to beat at that length.

Corpus: real FDA approval reviews and EMA assessment reports and labels, joined in a seeded random order into one PDF of at least 10,000 pages with extractable text, then put through the real extraction and chunker as one paper. It is a joined file, not a single real submission; say so. Scanned documents with no text layer are left out and counted.

Questions: 100 from one writer who runs no search and sees no ranking, working from pages sampled at random by a seeded script; fact, reworded, table number, multi-need. The key is a passage's words plus the document's page span, so the same sentence in another drug's document does not count. A seeded split makes dev 40 (failures may be read) and sealed 60 (opened once, after methods are fixed, for no more than 6 methods).

Score: every need reaches the model inside the budget, through the real retrieve and cut_to_budget wherever the method allows.

Always on the sealed set: A vectors top 8 (main today), V vectors at the budget, B the branch.
Dev may also try: more candidates, a bigger budget, HyDE, terms, section titles and numbers in tsv, section-first search, and anything research suggests from dev failures.

To replace B, on the sealed 60, a method must:
1. No new model, no migration: net +2, no document type falling.
2. A migration or a re-embed of every paper: net +3.
3. A second model: net +3 and under 3 s a question on CPU.
4. A model call per question: net +3, and a failed or slow call leaves the search as B.
5. A mix must beat its best part by at least 1.

Speed, B on the whole file: retrieve median under 1 s, slowest under 3 s. Otherwise B fails at this length whatever it scores.

Answers: winner against A on the sealed set with the free cloud model. Local: finish the 33 known questions with the disk guard, and a sample of the sealed set.

Ingest: the same file through the real worker: reaches ready with a kill -9 in the middle, a small paper finishes alongside it, worker peak memory recorded.

## Round 5, dev results before the sealed set (written 2026-11-05)

Scoring changed before the sealed set was read: a table's number and label may reach the model in different chunks, since 5 of 9 dev table keys failed only on being split. 38 of 40 dev questions score; 2 keys don't match the extracted text and stay out, counted.
Dev: A 20, V 22, B 29; budget 30,000 31 (+2 -0); 40,000 and 60,000 also 31. No gain: greedy fill, dedupe, HyDE, BM25 b .2, RRF k 20, caption rule, candidates 100 to 500. Worse: window trimming, term expansion. +1 only: k1 1.5, b .75.
Memory: worker peak 5.17 GB on the file. Arena off is worse (7.2 GB). Token limit: 8,192 5.51 GB; 2,048 2.46 GB; 1,024 1.34 GB; 512 1.02 GB on the 120 longest texts plus 300 random. Over 2,048 tokens: 33 of 19,852 chunks; over 1,024: 261.
Sealed methods, fixed now: A, V, B, budget 30,000, k1 1.5 + b .75, and the chosen token limit.

## Round 6: many documents (rules written 2026-11-05, before any run)

Corpus: every regulatory document with a text layer, plus the author's 400 library PDFs, each its own paper, about 565 papers. A throwaway database only.
Questions: the same dev and sealed sets; the right paper must supply the passage. Dev failures may be read; sealed opened once for this test.
Today: the workspace search, k 8, cap 3 per paper, 40 candidates.
To replace today's settings on the sealed set: no new model and no migration, net +2 and median under 1 s; same rules as round 5 otherwise.
Scale: search time at the real corpus, then with vectors copied to at least 500,000 chunks. Over 3 s at 500,000 counts against a method. Copies measure speed only, never answers.

## Round 5, sealed set at 10,226 pages, one run (2026-11-05)

58 of 60 score; 2 keys don't match the extracted text.
A 31, V 41, B 48 (A to B +17 -0; V to B +7 -0), budget 30,000 49 (+1 -0, fails +2), k1 1.5 + b .75 44 (-4). B median 0.40 s, slowest 0.77 s under load: passes the speed rule.
Winner: B at 24,000 characters. Research round 6 on dev: entity region focus 22-25 of 38 (loses), question splitting +0 -0.

Token limit in the real worker, same 10,226-page file, same kill at about half: worker peak 5.17 GB became 1.33 GB, median 1.05 GB. Recovery 9 s. Total 1,728 s, slower than the first 1,065 s because the many-documents build and an answer test ran at the same time; compare on an idle machine before quoting a speed. Sealed questions at the limit: 48 of 58, +0 -0 against no limit.

## Real answers, sealed 60 at 10,226 pages, free cloud models (2026-11-05)

A 30 right (31 given), B 45 (48 given), L best first and second best last 42 (48 given). A to B +15 -0. L vs B +2 -5: fails, ranked order stays. Median prompt A 2,984 tokens, B 6,593. Models: gemini 3.1 flash-lite 111, gpt-4o 65, gpt-4o-mini 3, gemini 3.5 flash 1; each question's three answers came from the same model.
Suites on the final code: backend 4,571 passed, 39 skipped; frontend 2,393 passed; tsc -b clean.

## Round 6 results (2026-11-05)

Dev, 562 papers, 75,554 chunks, 38 scored: today (k 8, cap 3, vectors) 16; hybrid switch on 21; hybrid + budget (HB) 24 at 1.9 s median; caps 5 to 40 and candidates 100 to 300 no gain; documents first (vector top 300 across papers, paper score = sum of its top 3 reciprocal ranks, top 10 papers, then hybrid + budget inside) 25 at 0.19 s; top 20 papers 25; top 3 21; rare-word paper filter 23-24 (loses); documents first with vectors only inside 17.
Sealed, one run, 59 scored: today 24, hybrid on 32 (1.4 s), HB 35 (1.4 s), documents first 41 (0.15 s). Today to documents first +17 -0; HB to documents first +6 -0. Passes round 6's rule.
Scale check next: five copies of the library to about 550,000 chunks; time on the original scope (graded, copies outside it) and on the whole library (speed only).

## Scale check and build (2026-11-05)

Five copies of the 562 papers: 552,597 chunks, 3,379 papers, 3.6 GB database.
Original 562 papers with the copies present (graded): today 16 (0.07 s median), hybrid + budget 24 (2.71 s median, 8.24 s slowest), documents first 24 (0.31 s, slowest 0.60 s). ef_search 200 brings documents first back to 25 at 0.22 s; left at 100, noted as a setting for very large libraries.
All 3,379 papers (speed only): documents first 0.48 s median, 2.77 s slowest. Passes the 3 s rule.
Built: retrieval.likely_papers and retrieve(words=...); workspace chat searches the 10 likeliest papers with keywords and vectors and fills 24,000 characters. Commit 0d699e0, tests shown red first. Token limit 1,024: commit 3eb81ce.

## Local model, sealed 60 at 10,226 pages (2026-11-05)

qwen3:8b through the real OllamaLLM: A 28 right (31 given), B 30 right (48 given), B vs A +11 -9. Median answer 11.7 s (A) and 26.7 s (B), slowest 32 s and 56 s; no 120 s timeout. The passage reaches the model far more often, but the 8B model cites the wrong one among 18 to 33 passages from many drugs: 18 of B's misses had the right passage in the prompt.

Rule for a local budget, written before the run: on the 40 dev questions with qwen3:8b, a 12,000-character budget for local models ships only if it is right at least 2 more times than B at 24,000 and no fewer times than A. Dev was used to tune retrieval, not answers; a pass is provisional until a new sealed set confirms it.
Local budget result, dev 40, qwen3:8b: A 18, B 19, 12,000 characters 20 (+4 -3 vs B). Fails the +2 rule: one budget for every model stays. Its 2 s median is Ollama's prompt cache (it ran right after B), not a real speed. With an 8B local model most of the retrieval gain is lost at the answer step; a larger local model or a cloud model gets it.

## Round 7: a second sealed set of 200 (rules written 2026-11-06, before any question exists)

Exact McNemar on the sealed results already in hand: long file A to B +17 -0 p<0.001; V to B +7 -0 p=0.016; many papers today to documents first +17 -0 p<0.001; HB to documents first +6 -0 p=0.031; cloud answers +15 -0 p<0.001; local qwen3:8b +11 -9 p=0.82.

New questions: two blind agents, 100 each, from pages not sampled before, same kinds and rules. All 200 are sealed: methods are fixed now and nothing is tuned on them.
Fixed methods: long file A, V, B; many papers today, hybrid switch on, documents first; cloud answers A and B; local answers A and B with qwen3:8b and with qwen2.5:14b.
Report each comparison with gained, lost and exact McNemar p. A result changes a decision only if p < 0.05 in the direction it claims.
Added 2026-11-06, before the 200 questions are run: BM25 alone under the same 24,000-character budget joins the fixed methods for the long file (a reviewer asked for it to separate the keyword half from the budget).
Also added 2026-11-06, before the 200 questions are run, after the methodology review:
- Confirmatory contrasts, two only: long file V vs B at the same 24,000-character budget; many papers HB vs documents first. Exact McNemar, alpha 0.05 each, reported first.
- Every other sealed contrast is exploratory: list them all with Holm-adjusted p.
- Also report a rank measure: the needed passage within the first 8 of the ranking, per method.
- Report results per question kind, and list every dropped question with its reason (key not in the extracted text).
- Cloud answers: record the model id per answer and report per model.

## Round 1 review rules (written 2026-11-06, before scoring or sampling)

Answer-text check (M13), fixed before any saved answer is scored:
- Normalise both answer and key string: lowercase; every Unicode dash or minus to "-"; "×" to "x"; non-breaking and other spaces to one space; collapse whitespace; drop thousands commas inside numbers (1,104 to 1104).
- A key string with digits is met when every number in it (regex -?\d+(\.\d+)?) appears among the answer's numbers, counting repeats, order free. "7x", "7-fold" and "7 times" all yield the number 7.
- A key string without digits is met when it is a substring of the answer, or when every word of 4 or more letters in it, other than these stop words (with, from, that, this, were, been, have, than, which, their, there, these, those, after, before, during, between, under, over), appears in the answer.
- A need is met when any alternative has all its strings met; a question is met when every need is met. A two-fact question needs both.
- Reported two ways: answer-text alone, and answer-text and right citation together.

Hand check of keys (M10), seed fixed before drawing: Python random.Random(20261106).sample over the 60 sealed questions of round 5 plus the 200 of round 7 in id order (L-ids, then M001-M100, then N001-N100), 50 keys. The author sees each question, its key strings, the source document and page text, and no method's outcome. Error categories: wrong answer, ambiguous question, answer in several documents, key string not unique, key on the wrong page. Report the error rate with a Wilson 95% interval. Keys found wrong: sealed comparisons are reported with them kept and with them removed.

Repeats (M14): cloud answers pinned to one model id and provider (github/gpt-4o-2024-11-20 through OmniRoute, temperature 0), two runs each of A and B on the 60 sealed questions; local qwen3:8b at temperature 0, two runs each of A and B. If the pinned model fails, three runs with whatever answers, model id recorded per answer.

## Change to the hand check, and a second domain (written 2026-11-06, before anything is drawn or run)

The author's field is software engineering and creativity, not medicine, and they will not judge drug-document keys. So:
- Second domain: the author's software-engineering and creativity papers (workspaces Creativity, SE Creativity, Music x SE creativity, Music creativity), copied into the throwaway database, each its own paper. A blind agent writes 100 questions from pages a seeded script samples (seed 20261107), same kinds and key rules; split by seed 5107 into 40 tuning and 60 sealed. Same fixed methods as round 6 (today, hybrid switch on, fused over every paper, documents first), plus the long-file methods on a joined file of the same papers if it reaches 5,000 pages.
- The author's hand check moves to this domain: Python random.Random(20261108).sample over its 100 questions in id order, 50 keys, same error categories and Wilson interval, no method outcomes shown.
- The 50 drug-document keys already drawn with seed 20261106 are audited instead by a model of another family (GPT-4o, pinned id, temperature 0) with the same categories, and that substitution is reported as weaker than a human check.
Author decision 2026-11-06: option B. The author checks only software-engineering and creativity keys. The pharma keys (sealed 60 and the 200) are audited by GPT-4o, and the abstract and RQ1 say they were written by a model and checked only by a second model.
GPT-4o audit rule, fixed before it runs: model github/gpt-4o-2024-11-20 through OmniRoute, temperature 0, max 300 tokens, one call per question. Input: the question, every key string, the source page's extracted text, and for each key string the list of other documents whose extracted text contains it. Output JSON {verdict, reason} with verdict one of ok, wrong_page, does_not_answer, ambiguous, not_unique, several_documents. A key counts as flawed for any verdict but ok. A call that fails or returns no valid verdict is retried once, then recorded as no_verdict and counted separately.
GPT-4o audit: the first 12 calls failed on a harness bug (the router streams unless told not to); those empty results were deleted and the audit restarted with stream off, nothing else changed (2026-11-06).
2026-11-06 02:05, GitHub's GPT-4o quota ran out ("all credentials cooling down"; the Cline route has no credit):
- Audit paused after 125 keys. The no_verdict entries written during the outage were removed, as the cause was quota and not the model; the rest of the keys are audited by the same GPT-4o once the quota resets.
- Pinned repeats (M14) switch, before any new run, to google gemini/gemini-3.1-flash-lite through OmniRoute, temperature 0, two runs each of A and B on the 60 sealed questions. The 29 GPT-4o answers already written are kept aside and not used.

## Round 7 results: sealed set 2 (2026-11-06)
Long file, 186 scored (14 keys not in the extracted text, listed): A 86, V 107, B 139, BM25 alone 144. Confirmatory V vs B: +35 -3, p<0.0001. B vs BM25 alone +12 -17 (p=0.46). Recall@8: A 86, V 86, B 103, BM25 alone 129. Not naming the drug (65): V 44 -> B 55, +11 -0, p=0.001.
Library, 189 scored: today 68, switch on 93, fused over every paper 97, documents first 105. Confirmatory HB vs documents first: +10 -2, p=0.039. Paper stage holds the target paper in its 10 for 187 of 189.
Library rebuilt: 165 regulatory documents and 397 library papers (3 library PDFs gave no chunks).
2026-11-06 01:36: audit calls that hit a 429 rate limit now wait for the reset the router names and retry, instead of counting as a failed call; a real failure is still retried once and then recorded as no_verdict. Pace 8 s between keys.
2026-11-06 01:40: GitHub's daily GPT-4o allowance is spent (cooldown repeats even after waiting). Audit paused at 78 of 260 keys; it resumes with the same model when the allowance resets.
Pinned repeats (M14), gemini/gemini-3.1-flash-lite, temperature 0, two runs: identical in both runs (60 of 60 answer texts the same, for A and B). Grounded A 31, B 46 (+15 -0, p=0.0001); answer text A 27, B 41 (+14 -0, p=0.0001).
Local repeats and the 14B model (written before the runs): the app's own Ollama request plus temperature 0 and seed 1; qwen3:8b two runs, qwen2.5:14b one run, each A and B on the 60 sealed questions; scored by citation and by the logged answer-text rule; local results also reported per kind and per error type (no citation, cites another drug's document, cites the right document but the wrong passage).

### 2026-11-06 — SE joined file: unmergeable PDFs
Written before the SE scoring runs. The first join stopped on a PDF with a malformed page tree. Any PDF that PyMuPDF can't merge is left out of the SE joined file, and its partial pages are removed. Each one is logged as `join_skip` in se_build.log. Questions whose key paper is left out drop from the joined-file score only; the scorer reports them as unreachable keys. The library score keeps every paper.

### 2026-11-06 — SE/creativity library: results
341 papers (one had no text layer) and 25,354 chunks.
- **Dev:** 35 of 40 questions scoreable. T 20, H8 20, HB 20, D10 21.
- **Sealed:** 57 of 60 scoreable. T 30, H8 29, HB 29, D10 28.
  - T→D10: +4 −6, p .75.
  - HB→D10: +0 −1, p 1.00.
  - T→H8: +4 −5, p 1.00.
  - The target paper is in D10's scope for 56 of 57.
- **Verdict:** the library gain does not transfer to this domain. No method separates from today's search.
- **Diagnosis** (post hoc, sealed misses). 23 questions are missed by every method. Inside its own paper the key chunk ranks a median of about 6 with keywords and about 18 with vectors alone (0-based). With 24,000 characters (about 25 chunks) spread over 9–10 papers, each paper gets roughly 2–3 chunks, too few.
- **Exploration** (dev only, not confirmatory): D3 22, D5 23, D20 20 of 35. These are within noise. No new rule was adopted, and the SE sealed set is now spent.

### 2026-11-06 — SE/creativity joined file (7,271 pages, 26,629 chunks): results
One PDF was left out by join_skip; it has no text layer and no scoreable question.
- **Dev:** 31 scoreable. A 19, V 23, B 26, K 20.
  - A→B: +7 −0, p .016.
  - V→B: +3 −0, p .25.
- **Sealed:** 54 scoreable. A 32, V 38, B 40, K 43.
  - A→B: +8 −0, p .008.
  - V→B: +4 −2, p .69.
  - B→K: +5 −2, p .45.
- **Recall@8:** A 32, V 32, B 35, K 36.
- **Verdict:** the shipped long-paper change (A→B) beats today's search in the second domain too. The keyword share of the gain is small here (V→B not significant). On the regulatory file it was the larger share, which fits exact drug, dose and section vocabulary.
- **Build note:** se_build was killed silently after chunking the joined file (no traceback, most likely memory). se_resume.py finished the 3,338 unembedded chunks; the others reused the separate papers' vectors.

### 2026-11-06 — S7: fused search's misses on long-file sealed set 2 (post hoc)
47 misses, analysed with s7_misses.py (out/s7_misses_B_sealed2.json).
- 44 sent at least one passage from the source document.
  - 22: the needed passage ranked within twice the number of passages sent (just past the budget).
  - 17: further down.
  - 5: not in the top 300.
- 3 sent nothing from the source document. All three are reworded questions.

### 2026-11-06 — Local qwen3:8b at temperature 0, seed 1, two runs (rule above)
The two runs are identical: 120 of 120 answers match word for word.
- **A (today):** cited 26, text 24, needed passage sent 31.
- **B (branch):** cited 30, text 32, needed passage sent 48.
- **A→B, cited:** +12 −8, p .50.
- **A→B, text:** +12 −4, p .077.
- **B per kind** (n, cited, text): fact 21, 11, 14; reworded 21, 15, 13; table 13, 3, 4; two-fact 5, 1, 1.
- **B's 30 uncited answers:** 18 had the needed passage sent but cited another; 12 never had it sent.
- **Verdict:** the earlier default-temperature text gain (p .007, one run) does not reach significance at temperature 0. The paper now reports the pinned runs as the main local result and the default run beside them. Timings come from a machine loaded by macOS media analysis and are not used.

## Local 14B result (qwen2.5:14b Q4_K_M, temperature 0, seed 1, one run; rule above)
- A: cited 23/60, text 25; B: cited 36/60, text 34.
- cited A→B +17 −4, exact McNemar p=0.007; text A→B +13 −4, p=0.049.
- Holm across the four local temperature-0 contrasts (8B cited .503, 8B text .077, 14B cited .007, 14B text .049): 14B cited .028 holds; 14B text .147, 8B text .154 do not.
- B per kind (n, cited, text): fact 21/12/17, multi 5/2/1, reworded 21/18/13, table 13/4/3.
- B uncited by cause: passage sent, other cited 12 (8B: 18); passage not sent 12 (same retrieval).
- Read: at 14B the budget gain carries into grounded answers; at 8B it does not. One run of one model; timings not used (machine busy).

## Auditor change (written before the run, 6 Nov ~04:30 UTC)
GPT-4o's free GitHub quota stopped the key audit at 78 of 260 regulatory keys (64 replies report gpt-4o-2024-11-20, 14 report no model, so the router may have answered those with another model). The audit continues with Llama 3.3 70B Instruct (OVH through the router, temperature 0), a family that neither wrote the questions (Claude) nor wrote cloud answers (Gemini, GPT-4o). Same prompt and inputs as audit_keys.py, on all 260 keys, so one auditor covers every key. GPT-4o's 64 model-confirmed verdicts are kept only for agreement (raw agreement, Cohen's kappa on ok against flagged). Sealed results are reported with all keys and without the keys Llama flags (any verdict other than ok). Llama also audits the author's 50 SE keys, and its verdicts are compared with the author's (kappa, ok against flagged). No method result is shown to the auditor.

## Idle-machine timings, reviewer M17 (written before the run, 6 Nov ~04:40 UTC)
No benchmark, ingest or local model running; only the key audit, which is network calls, and macOS services (StorageManagement about one core of 12). Docker VM unchanged (12 CPUs, 8 GB). Sealed set 2: long file A and B (bench5), library T, HB and D10 (bench6); one pass per question, in set order. Report median, p90 and max search time per method. The run must reproduce the earlier sealed-2 recall counts exactly; if it does not, the timings are reported as not comparable. Timing only, no new scoring decisions.
Result: recall reproduced exactly (long A 86, B 139 of 186; library T 68, HB 97, D10 105 of 189, D10 vs HB +10 −2). Seconds p50/p90/max: long A .03/.08/.49, B .27/.33/.57; library T .02/.03/.06, HB .96/1.19/1.97, D10 .11/.14/.16. All within the 1 s median / 3 s max rule.

## Reviewer M8, post hoc and descriptive (written before the run, 6 Nov ~04:45 UTC)
Library sealed set 2, methods HB and D10, rerun as scored. Per method: (1) share of sent passages from the 397 non-regulatory papers (distractors) and from regulatory documents of another drug; (2) document recall@10 = target paper among the ten D10 selects (already 187/189); (3) sibling scoring: a need also counts when its strings arrive from any document of the same active substance (EMA brand mapped to its FDA generic: brilique ticagrelor, eliquis apixaban, forxiga dapagliflozin, invokana canagliflozin, jardiance empagliflozin, entresto sacubitril, ozempic/rybelsus/wegovy semaglutide, mounjaro tirzepatide, pradaxa dabigatran, xarelto rivaroxaban; others are their own). Strict counts stay the paper's measure; sibling counts are reported beside them with McNemar for D10 vs HB. No decision rests on this.
Result: strict reproduced (HB 97, D10 105 of 189). Sibling: HB 98, D10 105; D10 vs HB +9 −2, p=0.065 (strict +10 −2, p=0.039). Sent passages from distractor papers: HB 4.3%, D10 3.9%; from other drugs' regulatory documents: HB 31.8%, D10 29.5%. Target paper in D10's ten: 187/189. Read: the documents-first confirmatory win depends on strict scoring; report it as fragile.

## Reviewer S10, memory repeats (written before the run, 6 Nov ~04:50 UTC)
memcap.py at limits 8,192, 2,048, 1,024 and 512, three repeats each, interleaved (round 1 all four limits, then round 2, then 3), each a fresh host process on the same 420 texts (300 random seed 7 + 120 longest of the long file). Peak = the process's ru_maxrss (macOS reports bytes). Report the range per limit. The worker figures (5.17 to 1.33 GB) were docker stats sampled every 2 s and are a different measurement; the paper says which is which. The full worker ingest is not repeated here: its timing needs an idle machine for 30+ minutes per run, and is left marked not comparable.
Result: peak GB over three runs: 8,192 6.32–6.58 (first measurement 5.51); 2,048 2.65 ×3 (first 2.46); 1,024 1.36 ×3 (first 1.34); 512 1.04–1.06 (first 1.02). Seconds: 72–74, 53, 39–40, 23–24. The ordering and the roughly fourfold cut at 1,024 hold; the 8,192 peak varies by about 0.3 GB and ran higher than the first measurement. Table memory now shows the repeat ranges.

### Result: key audit by Llama 3.3 70B (2026-11-06, under the auditor-change rule above)
- Regulatory keys: 248 ok, 5 several_documents, 3 wrong_page, 2 does_not_answer, 2 no verdict (N095, N100). Flagged: L031 L068 L077 L098 M067 N023 N063 N064 N066 N071.
- Agreement with GPT-4o on its 64 model-confirmed verdicts (ok vs flagged): 61/64, kappa 0.64.
- Without flagged keys (scripts/audit_sens.py, out/audit_sens.json): every sealed contrast keeps its direction. Confirmatory long V->B 34/2 p<.001 (n180); confirmatory library HB->D10 9/2 p=.065 (was .039), same fragility as the sibling scoring (M8). Set1 HB->D10 5/0 p=.063.
- SE keys: 49 ok, 1 no verdict (S029). Author hand check still 6/50, so the author-vs-Llama comparison waits.

## Review round 2 rules (written 2026-11-06 07:40, before any of these runs)

R2-1 Rank measure on the library (M4). Rerun bench6 on sealed set 2 (T, H8, HB, D10) and on the SE sealed library (T, H8, HB, D10) with one measure added: recall@8, every needed string from the right paper among the first eight chunks of the ranking the method sends from, before the budget cut. Methods unchanged. If any recall-at-budget count differs from the published one, both are reported with the cause.

R2-2 Answers on sealed set 2 (N2a, N8). All 200 questions; the 14 whose keys are missing from the text count as misses for every method, as on set 1. Same prompt, scoring and settings as on set 1: grounded (a cited passage holds the needed strings) is primary, answer text secondary.
- qwen2.5:14b, A (top 8, before) vs B (fused, budget), temperature 0, seed 1. Confirmatory: grounded A->B, alpha .05.
- qwen3:8b A, B and K8 (BM25 alone, top 8, no budget), temperature 0, seed 1. Exploratory: grounded A->B and B->K8.
- Pinned Gemini 3.1 Flash Lite, temperature 0, A vs B, if the router serves it. Exploratory: grounded A->B. If its quota ends, the run stops and what finished is reported as partial.
- Holm across the exploratory grounded contrasts; answer-text contrasts reported beside them, not corrected.
These results replace sealed set 1 as RQ3's headline; set 1 stays in the paper, marked exploratory.

### Result R2-1 (2026-11-06 07:42)
Every recall-at-budget count reproduced (library sealed 2: 68, 93, 97, 105 of 189; SE library sealed: 30, 29, 29, 28 of 57). Recall@8, library sealed 2: T 68, H8 93, HB 93, D10 96. SE library: 30, 29, 29, 28. SE file (saved earlier): A 32, V 32, B 35, K 36 of 54. Files: out/r8_lib_sealed2.json, secr/out/r8_se_lib_sealed.json.

- 2026-11-06 10:15: local R2-2 run paused by the author (laptop needed) at 181 of 400 qwen2.5:14b answers; nothing scored yet. The script skips saved answers on restart; temperature 0, seed 1, so a resumed run is the same run.

### Result R2-2, cloud part (2026-11-06 10:55)
Pinned Gemini 3.1 Flash Lite answered all 400 (router reported that model for every one). Grounded A 83, B 132 of 200: +49 -0, exact McNemar p 3.6e-15, paired bootstrap 95% CI +18 to +30 points. Answer text A 78, B 101: +29 -6, p 1.2e-4, CI +6 to +17. B grounded by kind: fact 52/70, reworded 53/70, table 20/44, two-fact 7/16 (A: 36, 35, 8, 4). B ungrounded 68: passage not sent 61, sent but another cited 7. Median prompt tokens 3,218 vs 6,624. Questions not naming the drug (67): 37 vs 53. Holm across the exploratory contrasts waits for the qwen3:8b run (paused); the cloud p is so small that no Holm factor up to 3 changes it. The confirmatory qwen2.5:14b contrast is unscored until its run finishes. File: out/r2_cloud.jsonl.
