"""Audit of the owner's 50 SE keys by a second model, same prompt as audit_keys.py. Rule fixed in the log first. A rerun skips done ones."""
import glob, json, os, re, sys, time, httpx, pymupdf
B=os.path.expanduser("~/.cache/paperlab-bench"); ITEMS=sys.argv[1]; OUT=os.environ["AUDIT_OUT"]; MODEL=os.environ["AUDIT_MODEL"]; KEY=os.environ["OMNI_KEY"]
src=open(f"{B}/scripts/audit_keys.py").read()
exec(src[src.index("SYS="):src.index("def page_for")]); exec(src[src.index("def ask"):src.index("for q in Q")])  # SYS and ask(): the very same prompt and retry logic
norm=lambda s:" ".join(s.lower().split())
title={}; text={}
for l in open(f"{B}/secr/papers.tsv"):
    pid,_,_,t=l.rstrip("\n").split("\t")[:4]; title[pid]=t
for f in glob.glob(f"{B}/secr/pdfs/*.pdf"):
    pid=os.path.basename(f)[:-4]
    try: d=pymupdf.open(f); text[pid]=norm(" ".join(p.get_text() for p in d)); d.close()
    except Exception: pass
done={json.loads(l)["id"] for l in open(OUT)} if os.path.exists(OUT) else set()
for f in sorted(glob.glob(f"{ITEMS}/*.json")):
    q=json.load(open(f)); qid=os.path.basename(f)[:-5]
    if qid in done: continue
    parts=[f"Question: {q['question']}",f"Document: {q['doc']}"]
    for n,need in enumerate(q["keys"],1):
        for a,alt in enumerate(need,1):
            for w in alt:
                others=sorted({title[p] for p,t in text.items() if title.get(p)!=q["doc"] and norm(w) in t})
                parts.append(f"Fact {n}, option {a}, key string: \"{w}\" | also found in other documents: {', '.join(others[:8]) if others else 'none'}{' (+%d more)'%(len(others)-8) if len(others)>8 else ''}")
        pg=q["pages"][min(n-1,len(q["pages"])-1)] if q.get("pages") else {"text":""}
        parts.append(f"Page shown for fact {n}:\n{pg['text'][:5000]}")
    v,m=ask("\n\n".join(parts))
    open(OUT,"a").write(json.dumps(dict(id=qid,model=m,**v))+"\n"); print(qid,v["verdict"],flush=True); time.sleep(2)
print("SE_AUDIT_DONE",flush=True)
