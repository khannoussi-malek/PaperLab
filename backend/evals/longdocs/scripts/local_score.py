"""Score local temperature-0 runs: citation (grounded) and the answer-text rule from analysis1, A vs B, run-to-run agreement, per kind. argv: jsonl files."""
import json, math, re, collections, sys, os, yaml
B=os.path.expanduser("~/.cache/paperlab-bench"); Q={q["id"]:q for q in yaml.safe_load(open(B+"/q/"+os.environ.get("QSET","sealed")+".yaml"))}
src=open(B+"/scripts/analysis1.py").read(); ns={"re":re,"collections":collections,"math":math}
exec(src[src.index("STOP=set("):src.index('print("=== answer-text')],ns)
for name in ("mcn",):
    exec(src[src.index("def mcn"):src.index("def boot")],ns)
qmet,mcn=ns["qmet"],ns["mcn"]
runs={}
for f in sys.argv[1:]:
    by=collections.defaultdict(dict)
    for r in map(json.loads,open(B+"/out/"+f)): by[r["cfg"]][r["id"]]=r
    runs[f]=by
    for c in ("A","B"):
        ids=[i for i in by[c] if i in Q]
        print(f"{f} {c}: cited {sum(by[c][i]['right'] for i in ids)}/{len(ids)} text {sum(qmet(Q[i],by[c][i]['answer']) for i in ids)} given {sum(by[c][i]['given'] for i in ids)}")
    for lab,fn in (("cited",lambda r,i:r["right"]),("text",lambda r,i:qmet(Q[i],r["answer"]))):
        ids=sorted(set(by["A"])&set(by["B"])&set(Q)); x={i:fn(by["A"][i],i) for i in ids}; y={i:fn(by["B"][i],i) for i in ids}
        g=sum(y[i] and not x[i] for i in ids); l=sum(x[i] and not y[i] for i in ids); print(f"  {lab} A->B +{g} -{l} p={mcn(g,l):.3f}")
    kinds=collections.defaultdict(lambda:[0,0,0])
    for i in by["B"]:
        if i in Q: k=kinds[Q[i]["kind"]]; k[0]+=1; k[1]+=by["B"][i]["right"]; k[2]+=qmet(Q[i],by["B"][i]["answer"])
    print("  B per kind (n, cited, text):",dict(kinds))
    miss=collections.Counter()
    for i in by["B"]:
        r=by["B"][i]
        if i in Q and not r["right"]: miss["passage sent, other cited" if r["given"] else "passage not sent"]+=1
    print("  B uncited by cause:",dict(miss))
fs=list(runs)
if len(fs)>=2:
    a,b=runs[fs[0]],runs[fs[1]]
    for c in ("A","B"):
        ids=sorted(set(a[c])&set(b[c])); same=sum(a[c][i]["answer"]==b[c][i]["answer"] for i in ids); cit=sum(a[c][i]["right"]==b[c][i]["right"] for i in ids)
        print(f"repeat {c}: identical answers {same}/{len(ids)}, same citation verdict {cit}/{len(ids)}")
