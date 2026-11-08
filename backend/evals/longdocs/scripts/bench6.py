"""Round 6: many documents, each its own paper. Real retrieve; the right paper must supply the passage. argv: dev|sealed methods. Throwaway DB only."""
import asyncio, collections, json, os, re, statistics as st, sys, time, uuid, yaml
from unittest.mock import patch
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import select, text
from app.config import settings
from app.core import retrieval
from app.core.chat import cut_to_budget
from app.db import SessionLocal
from app.providers.embedding import get_model
S=os.environ["S"]; SET=sys.argv[1]; WANT=sys.argv[2].split(",")
Q=yaml.safe_load(open(f"{S}/q/{SET}.yaml")); norm=lambda s:" ".join(str(s).lower().split())
M={"T":dict(k=8,hybrid=False,budget=None),"H8":dict(k=8,budget=None),"HB":dict(k=40),
   "C5":dict(k=40,cap=5),"C10":dict(k=40,cap=10),"C20":dict(k=40,cap=40),
   "C10_100":dict(k=40,cap=10,cand=100),"C20_100":dict(k=40,cap=40,cand=100),"C20_300":dict(k=40,cap=40,cand=300),
   "D3":dict(k=40,doc=3),"D5":dict(k=40,doc=5),"D10":dict(k=40,doc=10),"D20":dict(k=40,doc=20),"DE10":dict(k=40,doc=10,rare=10),"DE20":dict(k=40,doc=10,rare=20),"DE40":dict(k=40,doc=10,rare=40),"D10V":dict(k=40,doc=10,hybrid=False),"D10E100":dict(k=40,doc=10,ef=100),"D10E200":dict(k=40,doc=10,ef=200),"D10E400":dict(k=40,doc=10,ef=400),"D5C":dict(k=40,doc=5,cap=5),"D10C":dict(k=40,doc=10,cap=5),
   # round R3: adaptive scope (largest score drop) and per-rank chunk caps
   "DG":dict(k=40,doc=10,gap=True),"DQ6_2":dict(k=40,doc=10,q1=6,q2=2),"DQ6_3":dict(k=40,doc=10,q1=6,q2=3),"DQ10_2":dict(k=40,doc=10,q1=10,q2=2),"DQ10_3":dict(k=40,doc=10,q1=10,q2=3),
   "DGQ6_2":dict(k=40,doc=10,gap=True,q1=6,q2=2),"DGQ10_2":dict(k=40,doc=10,gap=True,q1=10,q2=2)}
def met(need,chunks,paper):
    tx=[x for p,x in chunks if p==paper]
    return any(all(any(norm(w) in x for x in tx) for w in a["all_of"]) for a in need)
async def rare_papers(q,ids,most):
    async with SessionLocal() as s:
        terms=(await s.execute(text("select lexeme from unnest(tsvector_to_array(to_tsvector('english', :q))) as lexeme"),{"q":q})).scalars().all()
        df={}
        for w in terms:
            df[w]=(await s.execute(text("select array_agg(distinct paper_id) from chunks where paper_id = any(:ids) and tsv @@ quote_literal(:w)::tsquery"),{"ids":ids,"w":w})).scalar() or []
        await s.rollback()
    ok=sorted((w for w in df if 1<=len(df[w])<=most),key=lambda w:len(df[w]))
    return list(df[ok[0]]) if ok else ids
async def docs_first(q,ids,cfg,model):
    if cfg.get("rare"): ids=await rare_papers(q,ids,cfg["rare"])
    async with SessionLocal() as s:
        with patch.object(retrieval,"CANDIDATES",300):
            f=await retrieval.retrieve(s,q,paper_ids=ids,k=300,per_paper=300,embedder=model); await s.rollback()
    per=collections.defaultdict(list)
    for r,c in enumerate(f): per[c.paper_id].append(1/(60+r))
    score={p:sum(sorted(v,reverse=True)[:3]) for p,v in per.items()}
    top=sorted(score,key=score.get,reverse=True)[:cfg["doc"]]
    if cfg.get("gap") and len(top)>1:  # Adaptive-k on paper scores: cut at the largest drop
        s=[score[p] for p in top]; cut=max(range(len(s)-1),key=lambda i:s[i]-s[i+1]); top=top[:cut+1]
    return top
async def run(cfg,q,ids,model):
    ef=patch.object(settings,"hnsw_ef_search",cfg.get("ef",settings.hnsw_ef_search)); ef.start()
    t=time.perf_counter(); scope=ids
    if cfg.get("doc"): scope=await docs_first(q,ids,cfg,model)
    ctx=[patch.object(retrieval,"CANDIDATES",cfg.get("cand",retrieval.CANDIDATES))]
    if cfg.get("hybrid",True): ctx.append(patch.object(settings,"hybrid_search",True))
    for c in ctx: c.start()
    try:
        async with SessionLocal() as s:
            cap=cfg.get("cap",3 if len(scope)>1 else None); k=cfg["k"]
            if cfg.get("q1") and len(scope)>1: cap,k=cfg["q1"],2*cfg["k"]
            found=await retrieval.retrieve(s,q,paper_ids=list(scope),k=k,per_paper=cap,embedder=model); await s.rollback()
            if cfg.get("q1") and len(scope)>1:  # rank-1 paper keeps q1 chunks, the others q2
                first=scope[0]; seen=collections.Counter(); kept=[]
                for c in found:
                    seen[c.paper_id]+=1
                    if seen[c.paper_id]<=(cfg["q1"] if c.paper_id==first else cfg["q2"]): kept.append(c)
                found=kept[:cfg["k"]]
    finally:
        for c in ctx: c.stop()
    dt=time.perf_counter()-t; ef.stop(); b=cfg.get("budget",24000); sent=cut_to_budget(found,b) if b else found
    return [(c.paper_id,norm(c.text)) for c in sent],dt,sum(len(c.text) for c in sent),len({c.paper_id for c in sent}),scope,[(c.paper_id,norm(c.text)) for c in found[:8]]
async def main():
    model=get_model()
    async with SessionLocal() as s:
        PFX=os.environ.get("LIBPREFIX","")
        rows=(await s.execute(text("select id,title from papers where title like :pat and status='ready' and title not like 'copy%' and (:pfx<>'' or title not like 'se\_%')"),{"pat":PFX+"%.pdf","pfx":PFX})).all()
        ids=[r.id for r in rows]; byname={r.title[len(PFX):]:r.id for r in rows}
        if os.environ.get("SCOPE")=="all": ids=[r[0] for r in (await s.execute(text("select id from papers where title like '%.pdf' and status='ready'"))).all()]
        pool=(await s.execute(text("select paper_id,text from chunks where paper_id = any(:ids)"),{"ids":[r.id for r in rows]})).all()
    allc=[(p,norm(x)) for p,x in pool]; good=[]; dropped=collections.Counter(); where={}
    for q in Q:
        pp=[]; fine=q["doc"] in byname
        for need in q["needs"] if fine else []:
            own=byname[q["doc"]]
            if met(need,allc,own): pp.append(own)
            elif q["kind"]=="multi":
                hit=[i for i in ids if met(need,allc,i)]
                if len(hit)==1: pp.append(hit[0])
                else: fine=False
            else: fine=False
        if fine: good.append(q); where[q["id"]]=pp
        else: dropped[q["kind"]]+=1
    print(SET,"papers",len(ids),"chunks",len(allc),"questions",len(good),"of",len(Q),"dropped",dict(dropped),flush=True)
    res={}; TM={}; R8={}
    for name in WANT:
        cfg=M[name]; got={}; r8={}; took=[]; ch=[]; np=[]; inscope=0
        for q in good:
            sent,dt,c,n,scope,top8=await run(cfg,q["question"],ids,model); took.append(dt); ch.append(c); np.append(n)
            inscope+=where[q["id"]][0] in set(scope)
            got[q["id"]]=all(met(nd,sent,p) for nd,p in zip(q["needs"],where[q["id"]])); r8[q["id"]]=all(met(nd,top8,p) for nd,p in zip(q["needs"],where[q["id"]]))
        TM[name]=took; res[name]=got; R8[name]=r8; kinds=collections.Counter(q["kind"] for q in good if got[q["id"]]); ref=res.get("HB"); diff=""
        if ref and name!="HB": diff=f" vs HB +{sum(got[i] and not ref[i] for i in got)} -{sum(ref[i] and not got[i] for i in got)}"
        print(f"{name:8} {sum(got.values()):3} of {len(good)} {dict(sorted(kinds.items()))} seconds median {st.median(took):.2f} max {max(took):.2f} chars {int(st.median(ch))} papers {st.median(np):.0f}{diff}"+f" recall@8 {sum(r8.values())}"+(f" target paper in scope {inscope}/{len(good)}" if cfg.get("doc") else ""),flush=True)
    json.dump(res,open(f"{S}/out/bench6_{SET}_{'_'.join(WANT)[:50]}.json","w"))
    if os.environ.get("R8OUT"): json.dump(R8,open(os.environ["R8OUT"],"w"))
    if os.environ.get("TIMES"): json.dump(TM,open(os.environ["TIMES"],"w"))
asyncio.run(main())
