"""Every document as its own paper: reuses vectors by text, embeds the rest one at a time. A rerun skips finished papers. Throwaway DB only."""
import asyncio, glob, json, os, sys, time
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import text
from app.core import papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import Paper
from app.providers import embedding
from app.providers.extraction import extract
S=os.environ["S"]; OLD=open(f"{S}/pass/pid").read().strip()
rows=json.load(open(f"{S}/out/pdfs.json"))
docs=[(r["f"],f"{S}/pdfs/{r['f']}") for r in rows if r.get("good",0)>=.5]+[("lib_"+os.path.basename(f),f) for f in sorted(glob.glob(os.path.expanduser("~/Desktop/paperlab-pdfs/*.pdf")))]
async def main():
    m=embedding.get_model(); t0=time.time(); done=0
    async with SessionLocal() as s: have={r[0] for r in (await s.execute(text("select title from papers where status='ready' and title like '%.pdf'"))).all()}
    for name,path in docs:
        if name in have: continue
        try: d=chunk_blocks(extract(path).blocks)
        except Exception as e: print("skip",name,type(e).__name__,flush=True); continue
        if not d: print("empty",name,flush=True); continue
        async with SessionLocal() as s:
            await s.execute(text("delete from papers where title=:t"),{"t":name}); await s.commit()
            p=Paper(title=name,file_path=path,status="embedding"); s.add(p); await s.commit(); pid=p.id
            await papers.replace_chunks(s,pid,d)
            await s.execute(text("update chunks n set embedding=o.embedding, embed_model=o.embed_model from chunks o where o.paper_id=:old and n.paper_id=:new and o.text=n.text"),{"old":OLD,"new":pid}); await s.commit()
            todo=(await s.execute(text("select id,text from chunks where paper_id=:p and embedding is null"),{"p":pid})).all()
        for i in range(0,len(todo),16):
            part=todo[i:i+16]; V=[]
            for x in part: V+=await embedding.embed_documents(m,[x.text])
            async with SessionLocal() as s:
                await papers.set_embeddings(s,[x.id for x in part],V,m.name); await s.commit()
        async with SessionLocal() as s:
            await s.execute(text("update papers set status='ready' where id=:p"),{"p":pid}); await s.commit()
        done+=1
        if done%25==0: print("papers",done,"seconds",round(time.time()-t0),flush=True)
    print("MANY_DONE",done,round(time.time()-t0),flush=True)
asyncio.run(main())
