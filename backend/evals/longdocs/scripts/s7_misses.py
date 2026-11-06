"""S7: why fused search (B) missed on long-file sealed set 2. For each miss: did any sent passage come from the source document, and where does the needed passage rank in the fused list. Throwaway DB only."""
import asyncio, collections, json, os, uuid, yaml
assert "55434/passrule" in os.environ["DATABASE_URL"]
from app.core import retrieval
from app.core.chat import cut_to_budget
from app.db import SessionLocal
from app.providers.embedding import get_model
S=os.environ["S"]; norm=lambda s:" ".join(str(s).lower().split())
PID=uuid.UUID(open(f"{S}/pass/pid").read().strip()); F=json.load(open(f"{S}/pass/fixture.json")); SPAN={r["file"]:(r["start"],r["end"]) for r in F["rows"]}
Q={x["id"]:x for x in yaml.safe_load(open(f"{S}/q/sealed2.yaml"))}
D=json.load(open(f"{S}/out/detail5_sealed2_A_V_B_K.json"))["B"]
ok=lambda v:v["ok"] if isinstance(v,dict) else v
miss=[i for i,v in D.items() if not ok(v)]
def rank(need,found,span):
    best=None
    for a in need:
        rs=[]
        for w in a["all_of"]:
            r=next((k for k,c in enumerate(found) if span[0]<=c.page<=span[1] and norm(w) in norm(c.text)),None); rs.append(r)
        if None not in rs and (best is None or max(rs)<best): best=max(rs)
    return best
async def main():
    m=get_model(); cat=collections.Counter(); rows=[]
    async with SessionLocal() as s:
        for i in miss:
            q=Q[i]; docs=[q["doc"]]+[x for x in q.get("docs",[])[1:]] if q.get("docs") else [q["doc"]]
            found=await retrieval.retrieve(s,q["question"],paper_ids=[PID],k=300,embedder=m)
            sent=cut_to_budget(found); n=len(sent); span=SPAN[q["doc"]]
            src=any(span[0]<=c.page<=span[1] for c in sent)
            rs=[rank(need,found,SPAN.get(q["doc"])) for need in q["needs"]]
            worst=None if None in rs else max(rs)
            c=("absent from top 300" if worst is None else "just past the budget" if worst<2*n else "far down")
            c=("source document sent, " if src else "source document not sent, ")+c
            cat[c]+=1; rows.append(dict(id=i,kind=q["kind"],sent=n,ranks=rs,source_sent=src,cat=c))
        await s.rollback()
    for k,v in cat.most_common(): print(v,k)
    print("by kind",collections.Counter((r["kind"],r["source_sent"]) for r in rows))
    json.dump(rows,open(f"{S}/out/s7_misses_B_sealed2.json","w"),indent=1)
asyncio.run(main())
