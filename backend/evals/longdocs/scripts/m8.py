"""M8, descriptive: distractor share, document recall@10 and sibling scoring for HB and D10 on library sealed 2. Throwaway DB only."""
import sys, json, os
sys.argv=[sys.argv[0],"sealed2","HB,D10"]
src=open(os.path.join(os.path.dirname(__file__),"bench6.py")).read(); exec(src[:src.index("async def main")])
GEN=dict(brilique="ticagrelor",eliquis="apixaban",forxiga="dapagliflozin",invokana="canagliflozin",jardiance="empagliflozin",entresto="sacubitril",ozempic="semaglutide",rybelsus="semaglutide",wegovy="semaglutide",mounjaro="tirzepatide",pradaxa="dabigatran",xarelto="rivaroxaban")
REG={r["f"] for r in json.load(open(f"{S}/out/pdfs.json"))}
drug=lambda f: GEN.get(f.split("_")[1],f.split("_")[1]) if f in REG else None
async def main():
    model=get_model()
    async with SessionLocal() as s:
        rows=(await s.execute(text("select id,title from papers where title like '%.pdf' and status='ready' and title not like 'copy%' and title not like 'se\\_%'"))).all()
        ids=[r.id for r in rows]; name={r.id:r.title for r in rows}; byname={r.title:r.id for r in rows}
        pool=(await s.execute(text("select paper_id,text from chunks where paper_id = any(:ids)"),{"ids":ids})).all()
    allc=[(p,norm(x)) for p,x in pool]; good=[]; where={}
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
    out={}
    for m in WANT:
        cfg=M[m]; strict={}; sib={}; dist=other=tot=0; inscope=0
        for q in good:
            sent,_,_,_,scope=await run(cfg,q["question"],ids,model)
            inscope+=where[q["id"]][0] in set(scope)
            strict[q["id"]]=all(met(n,sent,p) for n,p in zip(q["needs"],where[q["id"]]))
            ok=True
            for n,p in zip(q["needs"],where[q["id"]]):
                fam=[i for i in ids if drug(name[i]) and drug(name[i])==drug(name[p])] or [p]
                ok&=any(met(n,sent,i) for i in fam)
            sib[q["id"]]=ok; d0=drug(q["doc"])
            for pid,_ in sent:
                tot+=1; dd=drug(name[pid])
                if dd is None: dist+=1
                elif dd!=d0: other+=1
        out[m]=dict(strict=strict,sib=sib)
        print(m,"strict",sum(strict.values()),"sibling",sum(sib.values()),"of",len(good),f"distractor share {dist/tot:.3f} other-drug share {other/tot:.3f}",f"target in scope {inscope}/{len(good)}" if cfg.get("doc") else "",flush=True)
    json.dump(out,open(f"{S}/out/m8_sealed2.json","w"))
    a,b=out["HB"]["sib"],out["D10"]["sib"]; g=sum(b[i] and not a[i] for i in a); l=sum(a[i] and not b[i] for i in a)
    from math import comb; n=g+l; p=min(1,2*sum(comb(n,k) for k in range(0,min(g,l)+1))/2**n) if n else 1
    print(f"sibling D10 vs HB +{g} -{l} p={p:.3f}",flush=True)
asyncio.run(main())
