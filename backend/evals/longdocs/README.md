# Long documents and large libraries: benchmark release

Everything needed to check or rerun the benchmark behind `../long-documents.md` and the paper "What Works for Retrieval over Long Regulatory Collections on a Laptop". Runs were made on 5 and 6 November 2026.

## Contents

| Path | What it holds |
|---|---|
| `documents.csv` | The 174 FDA and EMA documents: file name, source URL, download date, pages, share of pages with a text layer, and where each sits in the joined file |
| `questions/` | Question sets with their keys (exact strings from the source page) |
| `prompts/` | The question-writer prompts, word for word. The answer prompt is PaperLab's own, `backend/prompts/chat.v7.md` (built by `prepare` in `backend/app/core/chat.py`) at commit 0d699e0; the HyDE and term-expansion prompts are in `scripts/rewrites.py` |
| `scripts/` | The harness: download, build, ingest, score, answer, audit |
| `results/` | Per-question outcomes of every sealed run, the answers, and the per-key audit |
| `RULES.md` | The rules log: every pass rule and analysis rule, written before the run it governs, with the results that followed |

## Question sets

| File | Questions | Role |
|---|---|---|
| `pharma_long_dev.yaml` | 40 | tuning on the long file (failures were read) |
| `pharma_long_sealed.yaml` | 60 | sealed set 1 (scored in the runs listed in the paper's run table) |
| `pharma_long_sealed2_a.yaml`, `_b.yaml` | 100 + 100 | sealed set 2, confirmatory |
| `se_creativity_dev.yaml`, `se_creativity_sealed.yaml` | 40 + 60 | second domain: software-engineering and creativity papers |

Keys whose strings do not occur in PaperLab's extracted text cannot be met by any method; the scorer drops them and reports them (2 in sealed set 1, 14 in sealed set 2 on the long file).

The SE and creativity questions refer to papers by PaperLab id: those PDFs are the author's own library copies and are not redistributed.

## Seeds

| Seed | Use |
|---|---|
| 20261105 | order of documents in the joined file; pages sampled for the first question writer |
| 5105 | tuning/sealed split of the first 100 questions |
| 20261106 | pages for sealed set 2; the 50-key sample of regulatory keys |
| 20261107 | pages for the SE and creativity writer |
| 5107 | tuning/sealed split of the SE and creativity questions |
| 20261108 | the owner's 50-key hand check (SE and creativity) |
| 20261109 | order of papers in the SE and creativity joined file |

## Rerunning

The scripts expect a throwaway Postgres with pgvector on port 55434 (database `passrule`) and refuse any other database URL. They import PaperLab's backend (`PYTHONPATH=backend`) and read their working folder from `S` (for example `~/.cache/paperlab-bench`):

1. `fetch.py` downloads the documents into `$S/pdfs`; `inspect_pdfs.py` writes `$S/out/pdfs.json` (pages, and `good`, the share of pages with a text layer, as in `documents.csv`). Documents with `good` below 0.5 are left out.
2. `build10k.py` joins 70 of them into `$S/pass/fixture.pdf` and samples pages for the question writer.
3. `corpus10k.py` ingests the joined file as one paper; `corpus_many.py` ingests every document (and a library folder) as separate papers.
4. `bench5.py SET METHODS` scores the long file, `bench6.py SET METHODS` the library; both print per-kind results and write per-question JSON to `$S/out`.
5. `answers5.py` and `local5.py` ask a cloud model through an OpenAI-compatible router, or a local model through Ollama; `analysis1.py` computes the McNemar tests, intervals, Holm correction and the answer-text check.
6. `audit_keys.py` asks a second model to audit each key. Its defaults are GPT-4o's run; the Llama run set `AUDIT_MODEL=ovh/Meta-Llama-3_3-70B-Instruct` and `AUDIT_OUT=$S/out/audit_llama.jsonl`. Model names are the router's own.

The router (OmniRoute on `127.0.0.1:20128`, key in `OMNI_KEY`) is an external OpenAI-compatible service, not part of this release; any compatible endpoint serving the same models works.

The scripts read and write the working-folder names of the original run. To rerun from this folder, copy the files back under those names:

| Released | Working folder |
|---|---|
| `questions/pharma_long_dev.yaml`, `pharma_long_sealed.yaml` | `$S/q/dev.yaml`, `$S/q/sealed.yaml` |
| `questions/pharma_long_sealed2_a.yaml`, `_b.yaml` | `$S/q2/1/questions.yaml`, `$S/q2/2/questions.yaml` (joined as `$S/q/sealed2.yaml` for scoring) |
| `questions/se_creativity_*.yaml` | `$S/secr/q/dev.yaml`, `$S/secr/q/sealed.yaml` |
| `results/key_audit_llama.jsonl`, `key_audit_gpt4o_partial.jsonl` | `$S/out/audit_llama.jsonl`, `$S/out/audit_gpt4o.jsonl` |
| `results/answers_pinned_sealed2.jsonl` | `$S/out/r2_cloud.jsonl` (score with `QSET=sealed2 local_score.py r2_cloud.jsonl`) |
| `results/library_sealed2_rank8.json`, `se_library_sealed_rank8.json` | `$S/out/r8_lib_sealed2.json`, `$S/secr/out/r8_se_lib_sealed.json` (written by `r2_rank.sh`) |

`r2_local.sh` runs the local answers on sealed set 2. Its run was paused at 181 of 400 answers and is not yet released; it resumes where it stopped.

`bench5.py` runs `$S/scripts/bench5_extra.py` if it exists. That hook was never used: no such file was written, so no published number depends on it.

The SE and creativity runs (`se_*.py`) also need `$S/secr/papers.tsv` and the author's PDFs, which are not redistributed, so those runs can be checked from the per-question results but not rerun.

`m8.py` rescores the library counting sibling documents of the same active substance as hits; `memcap.py` measures peak embedding memory at each token limit.

`scale_copy.py` copies the library five times for the speed test; it is for speed only, never for scoring.

## Settings of the methods without a detectable benefit

| Method | Setting |
|---|---|
| Cross-encoder | `BAAI/bge-reranker-base` over the top 40 and the top 100; `ms-marco-MiniLM-L-12-v2` (FlashRank) over the top 40 |
| ColBERT | `answerai-colbert-small-v1` reranking the top 50 |
| SPLADE | SPLADE-v3 |
| Convex fusion | weight chosen on the other drug's questions, 0.1 to 0.9 |
| MMR | λ 0.8 and 0.9 over the top 40 |
| Page propagation | weight 0.5 |
| RM3 | 5 feedback passages, 10 terms, original query kept at 0.7 |
| Rocchio | question kept at 0.7, top 3 passages |
| HyDE, term expansion | GPT-4o, prompts in `scripts/rewrites.py` |

## Key checks

The regulatory keys were written by Claude Sonnet 5.5 and audited by Llama 3.3 70B Instruct (temperature 0) with the prompt in `scripts/audit_keys.py`. GPT-4o (`gpt-4o-2024-11-20`) began the audit and stopped at 78 keys when its free quota ran out; the router reports GPT-4o for 64 of them and no model for 14, so only those 64 are used, and for agreement only. `scripts/audit_sens.py` rescores the sealed sets without the keys Llama flags. Llama also audited the 50 SE and creativity keys that the author hand-checks (`scripts/se_audit.py`).
