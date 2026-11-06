"""The same chunks as a second paper, with chunks over the token limit embedded at that limit. argv: limit. The tree isn't touched."""
import asyncio, os, sys, time
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import text
from app.core import papers
from app.core.chunking import chunk_blocks
from app.db import SessionLocal
from app.models import Paper
from app.providers import embedding, onnx_embedding
from app.providers.extraction import extract
S=os.environ["S"]; CAP=int(sys.argv[1]); NAME=f"cap{CAP}"; OLD=open(f"{S}/pass/pid").read().strip()
onnx_embedding.MAX_TOKENS=CAP
async def main():
    d=chunk_blocks(extract(f"{S}/pass/fixture.pdf").blocks); m=embedding.get_model(); tok=m._embedder._tokenizer
    async with SessionLocal() as s:
        await s.execute(text("delete from papers where title=:t"),{"t":NAME}); await s.commit()
        p=Paper(title=NAME,file_path=f"{S}/pass/fixture.pdf",status="ready"); s.add(p); await s.commit(); pid=p.id
        await papers.replace_chunks(s,pid,d)
        await s.execute(text("update chunks n set embedding=o.embedding, embed_model=o.embed_model from chunks o where o.paper_id=:old and n.paper_id=:new and o.ordinal=n.ordinal"),{"old":OLD,"new":pid}); await s.commit()
        rows=(await s.execute(text("select id,text from chunks where paper_id=:p"),{"p":pid})).all()
    tok.no_truncation(); long=[r for r,e in zip(rows,tok.encode_batch([m.document_prefix+r.text for r in rows])) if len(e.ids)>CAP]; tok.enable_truncation(max_length=CAP)
    print("over the limit",len(long),"of",len(rows),flush=True)
    for i in range(0,len(long),16):
        part=long[i:i+16]; V=[]
        for x in part: V+=await embedding.embed_documents(m,[x.text])
        async with SessionLocal() as s:
            await papers.set_embeddings(s,[x.id for x in part],V,m.name); await s.commit()
    open(f"{S}/pass/pid_{NAME}","w").write(str(pid)); print("DONE",NAME,pid,flush=True)
asyncio.run(main())
