#!/bin/zsh
# Review round 2, rule R2-1: recall@8 for the library methods. Run from the repo's backend folder.
source $S/env.sh
R8OUT=$S/out/r8_lib_sealed2.json python $S/scripts/bench6.py sealed2 T,H8,HB,D10 2>&1 | grep -vE "Warning|warn"
S=$S/secr LIBPREFIX=se_ R8OUT=$S/out/r8_se_lib_sealed.json python $S/scripts/bench6.py sealed T,H8,HB,D10 2>&1 | grep -vE "Warning|warn"
echo R2_RANK_DONE
