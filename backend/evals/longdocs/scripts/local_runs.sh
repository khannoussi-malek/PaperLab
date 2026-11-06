#!/bin/zsh
source $S/env.sh; cd backend
for r in 1 2; do ollama stop qwen3:8b 2>/dev/null; nice -n 5 python $S/scripts/local5_t0.py qwen3:8b BA local_t0_r$r.jsonl > $S/out/local_t0_r$r.log 2>&1; tail -1 $S/out/local_t0_r$r.log; done
ollama stop qwen3:8b 2>/dev/null
nice -n 5 python $S/scripts/local5_t0.py qwen2.5:14b BA local14b_t0.jsonl > $S/out/local14b_t0.log 2>&1; tail -1 $S/out/local14b_t0.log
ollama stop qwen2.5:14b 2>/dev/null
echo LOCAL_RUNS_DONE
