"""The 10,226-page file as one paper with the branch's chunker and embedder, one text at a time. Throwaway DB only."""
import asyncio, os, time
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import text
from app.core import papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import Paper
from app.providers import embedding
from app.providers.extraction import extract
S=os.environ["S"]
async def main():
    t=time.time(); d=chunk_blocks(extract(f"{S}/pass/fixture.pdf").blocks); m=embedding.get_model()
    async with SessionLocal() as s:
        p=Paper(title="fixture10k",file_path=f"{S}/pass/fixture.pdf",status="ready"); s.add(p); await s.commit(); pid=p.id
        await papers.replace_chunks(s,pid,d)
        rows=(await s.execute(text("select id,text from chunks where paper_id=:p order by ordinal"),{"p":pid})).all()
    open(f"{S}/pass/pid","w").write(str(pid)); print("chunks",len(rows),flush=True)
    for i in range(0,len(rows),32):
        part=rows[i:i+32]; V=[]
        for x in part: V+=await embedding.embed_documents(m,[x.text])
        async with SessionLocal() as s: await papers.set_embeddings(s,[x.id for x in part],V,m.name); await s.commit()
        if i%3200==0: print("embedded",i,round(time.time()-t),flush=True)
    print("CORPUS10K_DONE",round(time.time()-t),flush=True)
asyncio.run(main())
