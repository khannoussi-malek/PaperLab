"""P7 duplicate check before sealing SE4: drop a question that matches an earlier SE question (dev, old sealed, SE3) or an earlier SE4 question exactly, has word-set Jaccard >= 0.5 with one, or repeats a key string from the same paper. Prints ids only, never question text."""
import os, re, yaml
S=os.path.expanduser("~/.cache/paperlab-bench/secr"); norm=lambda s:" ".join(str(s).lower().split())
words=lambda s:{w for w in re.findall(r"[a-z0-9]+",s.lower()) if len(w)>=3}
old=[q for f in ("q/dev.yaml","q/sealed.yaml","q3/questions.yaml") for q in yaml.safe_load(open(f"{S}/{f}"))]
new=[q for p in (1,2) for q in yaml.safe_load(open(f"{S}/q4/{p}/questions.yaml"))]
keys=lambda q:{(q["doc"],norm(w)) for need in q["needs"] for alt in need for w in alt["all_of"]}
kept=[]; dropped=[]
for q in new:
    hit=None
    for o in old+kept:
        a,b=words(q["question"]),words(o["question"]); j=len(a&b)/max(1,len(a|b))
        if norm(q["question"])==norm(o["question"]) or j>=0.5 or keys(q)&keys(o): hit=(o["id"],round(j,2)); break
    (dropped.append((q["id"],hit)) if hit else kept.append(q))
yaml.safe_dump(kept,open(f"{S}/q/sealed4.yaml","w"),allow_unicode=True,sort_keys=False)
print("SE4 written",len(new),"kept",len(kept),"dropped",len(dropped)); [print(" drop",i,"matches",h) for i,h in dropped]
