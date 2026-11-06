"""Finish se_joined after an interrupted se_build: embed what's missing, mark ready, write the pid. Throwaway DB only."""
import asyncio, os, sys
assert "55434/passrule" in os.environ["DATABASE_URL"]
sys.argv=["x"]; from sqlalchemy import text
from app.db import SessionLocal
from app.providers import embedding
exec(open(os.path.expanduser("~/.cache/paperlab-bench/scripts/se_build.py")).read().split("async def add")[0].split("ids=sorted")[0])
from app.core import papers
SE=os.path.expanduser("~/.cache/paperlab-bench/secr")
async def embed_missing(pid,m):
    async with SessionLocal() as s:
        todo=(await s.execute(text("select id,text from chunks where paper_id=:p and embedding is null"),{"p":pid})).all()
    for i in range(0,len(todo),16):
        part=todo[i:i+16]; V=[]
        for x in part: V+=await embedding.embed_documents(m,[x.text])
        async with SessionLocal() as s: await papers.set_embeddings(s,[x.id for x in part],V,m.name); await s.commit()
        if i%800==0: print("embedded",i,len(todo),flush=True)
async def main():
    async with SessionLocal() as s: pid=(await s.execute(text("select id from papers where title='se_joined'"))).scalar_one()
    await embed_missing(pid,embedding.get_model())
    async with SessionLocal() as s: await s.execute(text("update papers set status='ready' where id=:p"),{"p":pid}); await s.commit()
    open(f"{SE}/pass/pid","w").write(str(pid)); print("SE_DONE",pid,flush=True)
asyncio.run(main())
