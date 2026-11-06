"""Where does the key chunk rank inside its own paper? For SE sealed questions every library method missed. Throwaway DB only."""
import asyncio, json, os, yaml
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import text
from app.core import retrieval
from app.db import SessionLocal
from app.providers.embedding import get_model
S=os.environ["S"]; norm=lambda s:" ".join(str(s).lower().split())
Q={x["id"]:x for x in yaml.safe_load(open(f"{S}/q/sealed.yaml"))}
d=json.load(open(f"{S}/out/bench6_sealed_T_H8_HB_D10.json"))
miss=[i for i in d["T"] if not any(d[m][i] for m in d)]
async def main():
    m=get_model()
    async with SessionLocal() as s:
        byname={r.title[3:]:r.id for r in (await s.execute(text("select id,title from papers where title like 'se\\_%.pdf'"))).all()}
        for i in miss:
            q=Q[i]; pid=byname.get(q["doc"]); n=(await s.execute(text("select count(*) from chunks where paper_id=:p"),{"p":pid})).scalar()
            out=[i,q["kind"],"chunks",n]
            for words in (False,True):
                r=await retrieval.retrieve(s,q["question"],paper_ids=[pid],k=n,per_paper=n,embedder=m,words=words)
                txt=[norm(c.text) for c in r]
                ranks=[min([k for k,t in enumerate(txt) if norm(w) in t] or [None],key=lambda x:x if x is not None else 9e9) for need in q["needs"] for a in need[:1] for w in a["all_of"]]
                out+=["words" if words else "dense",ranks]
            print(*out,flush=True)
        await s.rollback()
asyncio.run(main())
