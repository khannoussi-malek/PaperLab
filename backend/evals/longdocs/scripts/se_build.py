"""SE/creativity domain: every paper as its own paper (title se_<id>.pdf), then a joined file of the same papers (seeded order) as one paper, reusing vectors by text. Throwaway DB only."""
import asyncio, json, os, random, time, pymupdf
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import text
from app.core import papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import Paper
from app.providers import embedding
from app.providers.extraction import extract
SE=os.path.expanduser("~/.cache/paperlab-bench/secr")
ids=sorted(l.split("\t")[0] for l in open(f"{SE}/papers.tsv"))
async def embed_missing(pid,m):
    async with SessionLocal() as s:
        todo=(await s.execute(text("select id,text from chunks where paper_id=:p and embedding is null"),{"p":pid})).all()
    for i in range(0,len(todo),16):
        part=todo[i:i+16]; V=[]
        for x in part: V+=await embedding.embed_documents(m,[x.text])
        async with SessionLocal() as s: await papers.set_embeddings(s,[x.id for x in part],V,m.name); await s.commit()
async def add(title,path,chunks,reuse_from_titles):
    async with SessionLocal() as s:
        await s.execute(text("delete from papers where title=:t"),{"t":title}); await s.commit()
        p=Paper(title=title,file_path=path,status="embedding"); s.add(p); await s.commit(); pid=p.id
        await papers.replace_chunks(s,pid,chunks)
        if reuse_from_titles:
            await s.execute(text("update chunks n set embedding=o.embedding, embed_model=o.embed_model from chunks o join papers op on op.id=o.paper_id where op.title like :pat and n.paper_id=:new and o.text=n.text and o.embedding is not null"),{"pat":reuse_from_titles,"new":pid}); await s.commit()
    return pid
async def main():
    m=embedding.get_model(); t0=time.time()
    async with SessionLocal() as s: have={r[0] for r in (await s.execute(text("select title from papers where title like 'se\\_%' and status='ready'"))).all()}
    for n,i in enumerate(ids):
        title=f"se_{i}.pdf"
        if title in have: continue
        try: d=chunk_blocks(extract(f"{SE}/pdfs/{i}.pdf").blocks)
        except Exception as e: print("skip",i,type(e).__name__,flush=True); continue
        if not d: print("empty",i,flush=True); continue
        pid=await add(title,f"{SE}/pdfs/{i}.pdf",d,None); await embed_missing(pid,m)
        async with SessionLocal() as s: await s.execute(text("update papers set status='ready' where id=:p"),{"p":pid}); await s.commit()
        if n%50==0: print("papers",n,round(time.time()-t0),flush=True)
    order=ids[:]; random.Random(20261109).shuffle(order); out=pymupdf.open(); rows=[]
    for i in order:
        try: d=pymupdf.open(f"{SE}/pdfs/{i}.pdf")
        except Exception: continue
        st=out.page_count+1
        try: out.insert_pdf(d)
        except Exception as e:
            if out.page_count>=st: out.delete_pages(st-1,out.page_count-1)
            print("join_skip",i,type(e).__name__,flush=True); d.close(); continue
        rows.append(dict(file=f"{i}.pdf",start=st,end=out.page_count)); d.close()
    out.save(f"{SE}/pass/fixture.pdf",garbage=1); json.dump(dict(rows=rows,pages=out.page_count),open(f"{SE}/pass/fixture.json","w")); print("joined pages",out.page_count,flush=True)
    d=chunk_blocks(extract(f"{SE}/pass/fixture.pdf").blocks); pid=await add("se_joined",f"{SE}/pass/fixture.pdf",d,"se\\_%"); await embed_missing(pid,m)
    async with SessionLocal() as s: await s.execute(text("update papers set status='ready' where id=:p"),{"p":pid}); await s.commit()
    open(f"{SE}/pass/pid","w").write(str(pid)); print("SE_DONE joined chunks",len(d),round(time.time()-t0),flush=True)
asyncio.run(main())
