"""GPT-4o audit of the pharma keys, rule fixed in the log before this ran. Saves each verdict; a rerun skips done ones."""
import json, os, re, sys, time, yaml, httpx, pymupdf
B=os.path.expanduser("~/.cache/paperlab-bench"); KEY=os.environ["OMNI_KEY"]; OUT=os.environ.get("AUDIT_OUT",f"{B}/out/audit_gpt4o.jsonl"); MODEL=os.environ.get("AUDIT_MODEL","github/gpt-4o-2024-11-20")
F=json.load(open(f"{B}/pass/fixture.json")); SPAN={r["file"]:(r["start"],r["end"]) for r in F["rows"]}
norm=lambda s:" ".join(s.lower().split())
docs=[r["f"] for r in json.load(open(f"{B}/out/pdfs.json")) if r.get("good",0)>=.5]
print("indexing",len(docs),"documents",flush=True); dtext={}
for f in docs:
    try:
        d=pymupdf.open(f"{B}/pdfs/{f}"); dtext[f]=norm(" ".join(p.get_text() for p in d)); d.close()
    except Exception: pass
fx=pymupdf.open(f"{B}/pass/fixture.pdf")
Q=sorted(yaml.safe_load(open(f"{B}/q/sealed.yaml")),key=lambda q:q["id"])+sorted(yaml.safe_load(open(f"{B}/q2/1/questions.yaml")),key=lambda q:q["id"])+sorted(yaml.safe_load(open(f"{B}/q2/2/questions.yaml")),key=lambda q:q["id"])
done={json.loads(l)["id"] for l in open(OUT)} if os.path.exists(OUT) else set()
SYS="You audit the answer keys of a document-search benchmark. Each key is exact text copied from a page; a search counts as right when that text reaches the reader. Judge only the key, never any search method. Reply with JSON only: {\"verdict\": one of \"ok\", \"wrong_page\", \"does_not_answer\", \"ambiguous\", \"not_unique\", \"several_documents\", \"reason\": one short sentence}. ok = the key text is on the page shown and answers the question, and the question has one clear answer. wrong_page = a key string is not on the page shown. does_not_answer = the key text is on the page but does not answer the question. ambiguous = the question could reasonably mean something else or has several valid answers. not_unique = the key text is too generic to prove the right passage was found. several_documents = other documents listed contain the key text and the question doesn't say which document it means."
def page_for(q,need):
    lo,hi=SPAN[q["doc"]]; w=norm(need[0]["all_of"][0])
    for p in [q["source_page"]]+list(range(lo,hi+1)):
        if lo<=p<=hi and w in norm(fx[p-1].get_text()): return p
    return q["source_page"]
def ask(prompt):
    tries=0
    while tries<2:
        try:
            r=httpx.post("http://127.0.0.1:20128/v1/chat/completions",headers={"Authorization":f"Bearer {KEY}"},timeout=120,json={"model":MODEL,"stream":False,"temperature":0,"max_tokens":300,"messages":[{"role":"system","content":SYS},{"role":"user","content":prompt}]})
        except httpx.HTTPError:
            tries+=1; time.sleep(20); continue
        if r.status_code==429:  # a rate limit is a wait, not a model failure
            try: wait=float(r.json()["error"].get("reset_seconds",40))
            except Exception: wait=40
            time.sleep(wait+5); continue
        try:
            d=r.json(); c=d["choices"][0]["message"]["content"]; m=re.search(r"\{.*\}",c,re.S); v=json.loads(m.group(0))
            if v.get("verdict") in ("ok","wrong_page","does_not_answer","ambiguous","not_unique","several_documents"): return v,d.get("model")
        except Exception: pass
        tries+=1; time.sleep(20)
    return {"verdict":"no_verdict","reason":"failed twice"},None
for q in Q:
    if q["id"] in done: continue
    parts=[f"Question: {q['question']}",f"Document: {q['doc']}"]
    for n,need in enumerate(q["needs"],1):
        p=page_for(q,need); txt=fx[p-1].get_text()[:5000]
        for a,alt in enumerate(need,1):
            for w in alt["all_of"]:
                others=[f for f,t in dtext.items() if f!=q["doc"] and norm(w) in t]
                parts.append(f"Fact {n}, option {a}, key string: \"{w}\" | also found in other documents: {', '.join(others[:8]) if others else 'none'}{' (+%d more)'%(len(others)-8) if len(others)>8 else ''}")
        parts.append(f"Page shown for fact {n}:\n{txt}")
    v,m=ask("\n\n".join(parts))
    open(OUT,"a").write(json.dumps(dict(id=q["id"],model=m,**v))+"\n"); print(q["id"],v["verdict"],flush=True); time.sleep(2)
print("AUDIT_DONE",flush=True)
