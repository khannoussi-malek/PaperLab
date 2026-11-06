"""How many needed passages sit in chunks over 1,024 tokens (the token-limit check, M15)."""
import json, os, uuid, yaml, asyncio
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Chunk
from app.providers import embedding
S=os.environ["S"]; PID=uuid.UUID(open(f"{S}/pass/pid").read().strip()); F=json.load(open(f"{S}/pass/fixture.json")); SPAN={r["file"]:(r["start"],r["end"]) for r in F["rows"]}
norm=lambda s:" ".join(str(s).lower().split())
async def main():
    m=embedding.get_model(); tok=m._embedder._tokenizer; tok.no_truncation()
    async with SessionLocal() as s: rows=(await s.execute(select(Chunk.page,Chunk.text).where(Chunk.paper_id==PID))).all()
    lens=[len(e.ids) for e in tok.encode_batch([m.document_prefix+r.text for r in rows])]
    over=[(r.page,norm(r.text)) for r,n in zip(rows,lens) if n>1024]; print("chunks",len(rows),"over 1,024 tokens",len(over))
    for name in ("dev","sealed"):
        Q=yaml.safe_load(open(f"{S}/q/{name}.yaml")); hit=0; strings=0
        for q in Q:
            lo,hi=SPAN[q["doc"]]; inq=False
            for need in q["needs"]:
                for a in need:
                    for w in a["all_of"]:
                        strings+=1
                        if any(lo<=p<=hi and norm(w) in x for p,x in over): inq=True
            hit+=inq
        print(name,"questions with a needed string inside an over-limit chunk:",hit,"of",len(Q))
asyncio.run(main())
