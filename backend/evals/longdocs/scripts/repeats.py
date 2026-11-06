"""Pinned-model repeats (M14): grounded and answer-text scores per run, run-to-run agreement, McNemar per run."""
import json, math, collections, os, sys
sys.path.insert(0, os.path.dirname(__file__))
B=os.path.expanduser("~/.cache/paperlab-bench")
src=open(f"{B}/scripts/analysis1.py").read(); g={}; exec(compile(src.split("print(\"=== sealed contrasts")[0],"a","exec"),g)
exec(compile(src[src.index("STOP=set("):src.index("print(\"=== answer-text check")],"b","exec"),g)
Q=g["Q"]; qmet=g["qmet"]; mcn=g["mcn"]
runs={}
for r in (1,2):
    by=collections.defaultdict(dict)
    for x in map(json.loads,open(f"{B}/out/answers_pinned_r{r}.jsonl")): by[x["cfg"]][x["id"]]=x
    runs[r]=by
for r,by in runs.items():
    models=collections.Counter(x["model"] for c in by.values() for x in c.values())
    line=[]
    for c in ("A","B"):
        cit=sum(x["right"] for x in by[c].values()); txt=sum(qmet(Q[i],x["answer"]) for i,x in by[c].items() if i in Q)
        line.append(f"{c}: cited {cit}/60 text {txt}/60")
    g_=sum(by["B"][i]["right"] and not by["A"][i]["right"] for i in by["A"]); l_=sum(by["A"][i]["right"] and not by["B"][i]["right"] for i in by["A"])
    tg=sum(qmet(Q[i],by["B"][i]["answer"]) and not qmet(Q[i],by["A"][i]["answer"]) for i in by["A"] if i in Q); tl=sum(qmet(Q[i],by["A"][i]["answer"]) and not qmet(Q[i],by["B"][i]["answer"]) for i in by["A"] if i in Q)
    print(f"run {r} models {dict(models)} | {' | '.join(line)} | cited A->B +{g_} -{l_} p={mcn(g_,l_):.4f} | text A->B +{tg} -{tl} p={mcn(tg,tl):.4f}")
for c in ("A","B"):
    a,b=runs[1][c],runs[2][c]; same=sum(a[i]["right"]==b[i]["right"] for i in a); same_t=sum(a[i]["answer"].strip()==b[i]["answer"].strip() for i in a)
    print(f"{c}: same grounded outcome in both runs {same}/60, identical answer text {same_t}/60")
