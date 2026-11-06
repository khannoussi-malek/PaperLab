#!/bin/zsh
# Review round 2, rule R2-2: local answers on sealed set 2. Run from the repo's backend folder.
source $S/env.sh
ollama stop qwen3:8b 2>/dev/null; nice -n 5 python $S/scripts/local5_t0.py qwen2.5:14b AB r2_14b.jsonl sealed2 > $S/out/r2_14b.log 2>&1; tail -1 $S/out/r2_14b.log
ollama stop qwen2.5:14b 2>/dev/null; nice -n 5 python $S/scripts/local5_t0.py qwen3:8b B,K8,A r2_8b.jsonl sealed2 > $S/out/r2_8b.log 2>&1; tail -1 $S/out/r2_8b.log
echo R2_LOCAL_DONE
