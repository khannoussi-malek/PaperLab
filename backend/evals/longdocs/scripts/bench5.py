"""Round 5: real retrieve and cut_to_budget on the 10,000-page file. argv: dev|sealed methods(comma). Throwaway DB only."""
import asyncio, collections, json, os, re, statistics as st, sys, time, types, uuid, yaml
from unittest.mock import patch
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import select
from app.core import retrieval
from app.core.chat import cut_to_budget
from app.db import SessionLocal
from app.models import Chunk
from app.providers import embedding
from app.providers.embedding import get_model
S=os.environ["S"]; SET=sys.argv[1]; WANT=sys.argv[2].split(",")
PID=uuid.UUID(os.environ.get("BENCH_PID") or open(f"{S}/pass/pid").read().strip()); F=json.load(open(f"{S}/pass/fixture.json")); SPAN={r["file"]:(r["start"],r["end"]) for r in F["rows"]}
Q=yaml.safe_load(open(f"{S}/q/{SET}.yaml")); RW=json.load(open(f"{S}/out/rewrites_{SET}.json")) if os.path.exists(f"{S}/out/rewrites_{SET}.json") else {}
norm=lambda s:" ".join(str(s).lower().split())
M={"A":dict(k=8,budget=None,vec=True),"V":dict(k=40,vec=True),"B":dict(k=40),"C100":dict(k=40,cand=100),"C200":dict(k=40,cand=200),"C500":dict(k=40,cand=500),"BUD40":dict(k=80,budget=40000),"BUD60":dict(k=100,budget=60000),
   "G":dict(k=40,fill=True),"G80":dict(k=80,fill=True),"G150":dict(k=150,fill=True),"GD80":dict(k=80,fill=True,dedupe=True),"D":dict(k=40,dedupe=True),"BUD30":dict(k=60,budget=30000),"B75":dict(k=40,bm25=(0.9,0.75)),"B20":dict(k=40,bm25=(0.9,0.2)),"K15":dict(k=40,bm25=(1.5,0.4)),"RRF20":dict(k=40,rrf=20),"G30":dict(k=80,fill=True,budget=30000),"W2000":dict(k=80,win=2000),"W1500":dict(k=80,win=1500),"W1000":dict(k=80,win=1000),"W700":dict(k=100,win=700),"B30B75":dict(k=60,budget=30000,bm25=(0.9,0.75)),"B30K15":dict(k=60,budget=30000,bm25=(1.5,0.4)),"K15B75":dict(k=40,bm25=(1.5,0.75)),"E1":dict(k=150,entity=1),"E2":dict(k=150,entity=2),"E1L5":dict(k=150,entity=1,least=5),"E2L5":dict(k=150,entity=2,least=5),"SPLIT":dict(k=40,split=True),"K":dict(k=40,bm25only=True),"K8":dict(k=8,bm25only=True,budget=None),"HYDE":dict(k=40,hyde=True),"TERMS":dict(k=40,terms=True),"HT":dict(k=40,hyde=True,terms=True)}
if os.path.exists(f"{S}/scripts/bench5_extra.py"): exec(open(f"{S}/scripts/bench5_extra.py").read())
def in_span(chunks,span): return [x for p,x in chunks if span[0]<=p<=span[1]]
def met(need,chunks,span):
    tx=in_span(chunks,span); return any(all(any(norm(w) in x for x in tx) for w in a["all_of"]) for a in need)
def fill(found,budget):
    out=[];used=0
    for c in found:
        if used+len(c.text)<=budget: out.append(c);used+=len(c.text)
    return out or found[:1]
STOP=set("the a an of in on for to and or with was were is are what how did does do by at from that this which when who than as be it its after before during had has have many much patients study".split())
def window(text,question,limit):
    """The part of a long chunk with the most of the question's words, so more passages fit the same budget."""
    if len(text)<=limit: return text
    low=text.lower(); words={w for w in re.findall(r"[a-z0-9.%-]{3,}",question.lower()) if w not in STOP}
    best=0;score=-1
    for start in range(0,len(text)-limit+1,100):
        part=low[start:start+limit]; s=sum(w in part for w in words)
        if s>score: best,score=start,s
    return text[best:best+limit]
def dedupe(found):
    seen=set();out=[]
    for c in found:
        k=norm(c.text)
        if k not in seen: seen.add(k);out.append(c)
    return out
ALL=[]; BUCKET=20
QSTOP=STOP|set("patients patient treatment dose group groups review studies clinical trial data rate results compared compare between much many following given taken".split())
def rare_terms(question,n):
    ws=[w for w in dict.fromkeys(re.findall(r"[a-z][a-z0-9-]{3,}|[a-z]*\d[a-z0-9-]{2,}",question.lower())) if w not in QSTOP]
    df={w:sum(w in x for _,x in ALL) for w in ws}; ws=[w for w in ws if df[w]>=3]
    return sorted(ws,key=lambda w:df[w])[:n]
def regions(terms,least):
    c=collections.Counter()
    for p,x in ALL:
        if any(w in x for w in terms): c[p//BUCKET]+=1
    return {b for b,n in c.items() if n>=least}
SPLIT=re.compile(r",? and (?=(?:what|how|which|when|who|did|does|do|was|were|is|are)\b)|\? ",re.I)
async def run(cfg,q,model):
    if cfg.get("split"):
        parts=[p for p in SPLIT.split(q["question"]) if len(p.split())>=4]
        if len(parts)>1:
            lists=[]; dts=[]
            for part in parts:
                _,dt,_,f=await run(dict(cfg,split=False,raw=True),dict(q,question=part),model); lists.append(f); dts.append(dt)
            seen=set(); merged=[]
            for i in range(max(map(len,lists))):
                for l in lists:
                    if i<len(l) and l[i].id not in seen: seen.add(l[i].id); merged.append(l[i])
            sent=cut_to_budget(merged,cfg.get("budget",24000))
            return [(c.page,norm(c.text)) for c in sent],sum(dts),sum(len(c.text) for c in sent),merged
    words=q["question"]; rw=RW.get(q["question"],{})
    if cfg.get("terms") and rw.get("terms"): words=q["question"]+" "+rw["terms"]
    ctx=[patch.object(retrieval,"CANDIDATES",cfg.get("cand",retrieval.CANDIDATES))]
    if cfg.get("vec"): ctx.append(patch.object(retrieval,"LONG_PAPER_CHUNKS",10**9))
    if cfg.get("bm25"): ctx+= [patch.object(retrieval,"BM25_K1",cfg["bm25"][0]),patch.object(retrieval,"BM25_B",cfg["bm25"][1])]
    if cfg.get("rrf"): ctx.append(patch.object(retrieval,"RRF_K",cfg["rrf"]))
    if cfg.get("bm25only"): ctx.append(patch.object(retrieval,"_HYBRID",retrieval._HYBRID.replace("SELECT id, rank FROM vector UNION ALL SELECT id, rank FROM lexical","SELECT id, rank FROM lexical")))
    real=embedding.embed_query; hyde=rw.get("hyde") if cfg.get("hyde") else None
    async def eq(m,t): return await real(m,hyde or t)
    ctx.append(patch.object(embedding,"embed_query",eq))
    for c in ctx: c.start()
    try:
        async with SessionLocal() as s:
            t=time.perf_counter(); found=await retrieval.retrieve(s,words,paper_ids=[PID],k=cfg["k"],embedder=model); dt=time.perf_counter()-t; await s.rollback()
    finally:
        for c in ctx: c.stop()
    if cfg.get("raw"): return None,dt,0,found
    if cfg.get("entity"):
        reg=regions(rare_terms(q["question"],cfg["entity"]),cfg.get("least",2))
        if reg: found=[c for c in found if c.page//BUCKET in reg][:cfg.get("keep",40)]+[c for c in found if c.page//BUCKET not in reg]
    if cfg.get("dedupe"): found=dedupe(found)
    if cfg.get("win"):
        found=[types.SimpleNamespace(page=c.page,text=window(c.text,q["question"],cfg["win"])) for c in found]
    b=cfg.get("budget",24000); sent=(fill(found,b) if cfg.get("fill") else cut_to_budget(found,b)) if b else found
    return [(c.page,norm(c.text)) for c in sent],dt,sum(len(c.text) for c in sent),[(c.page,norm(c.text)) for c in found]
async def main():
    model=get_model()
    async with SessionLocal() as s: rows=(await s.execute(select(Chunk.page,Chunk.text).where(Chunk.paper_id==PID))).all()
    allc=[(r.page,norm(r.text)) for r in rows]; ALL.extend(allc); good=[]; dropped=collections.Counter(); spans={}
    for q in Q:
        sp=[]; fine=True
        for need in q["needs"]:
            s0=SPAN.get(q["doc"]); hit=None
            if s0 and met(need,allc,s0): hit=s0
            else:  # a multi's second fact may sit in another document of the same drug
                other=[v for v in SPAN.values() if met(need,allc,v)]
                if q["kind"]=="multi" and len(other)==1: hit=other[0]
            if hit is None: fine=False
            sp.append(hit)
        if fine: good.append(q); spans[q["id"]]=sp
        else: dropped[q["kind"]]+=1
    print(SET,"questions",len(good),"of",len(Q),"dropped: words not in the extracted text",dict(dropped),flush=True)
    res={}; base=None; detail={}
    for name in WANT:
        cfg=M[name]; got={}; took=[]; ch=[]; detail[name]={}
        for q in good:
            sent,dt,c,found=await run(cfg,q,model); took.append(dt); ch.append(c)
            got[q["id"]]=all(met(n,sent,sp) for n,sp in zip(q["needs"],spans[q["id"]]))
            r8=all(met(n,found[:8],sp) for n,sp in zip(q["needs"],spans[q["id"]]))
            detail[name][q["id"]]=dict(ok=got[q["id"]],r8=r8,n=len(sent),chars=c,s=round(dt,3))
        res[name]=got; kinds=collections.Counter(q["kind"] for q in good if got[q["id"]])
        fam=collections.Counter(q["doc"].split("_")[0] for q in good if got[q["id"]])
        ref=res.get("B"); diff=""
        if ref and name!="B": diff=f" vs B +{sum(got[i] and not ref[i] for i in got)} -{sum(ref[i] and not got[i] for i in got)}"
        print(f"{name:7} {sum(got.values()):3} of {len(good)} {dict(sorted(kinds.items()))} {dict(fam)} seconds median {st.median(took):.2f} max {max(took):.2f} chars {int(st.median(ch))}{diff}",flush=True)
    json.dump(res,open(f"{S}/out/bench5_{SET}_{'_'.join(WANT)[:60]}.json","w")); json.dump(detail,open(f"{S}/out/detail5_{SET}_{'_'.join(WANT)[:60]}.json","w"))
    for name in WANT:
        d=detail[name].values(); print(f"{name:7} recall@8 {sum(x['r8'] for x in d)}  mean passages {sum(x['n'] for x in d)/len(d):.1f}  mean chars {sum(x['chars'] for x in d)/len(d):.0f}",flush=True)
asyncio.run(main())
