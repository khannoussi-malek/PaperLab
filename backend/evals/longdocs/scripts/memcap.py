"""Tokens per chunk, then peak memory on the 300 random + 120 longest texts with the token limit changed. argv: limit."""
import asyncio, os, random, resource, sys, time, uuid
import numpy as np
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Chunk
from app.providers import embedding, onnx_embedding
cap=int(sys.argv[1]); onnx_embedding.MAX_TOKENS=cap
async def main():
    S=os.environ["S"]; PID=uuid.UUID(open(f"{S}/pass/pid").read().strip())
    async with SessionLocal() as s: t=[r.text for r in (await s.execute(select(Chunk.text).where(Chunk.paper_id==PID))).all()]
    t.sort(key=len); rng=random.Random(7); ts=rng.sample(t,300)+t[-120:]; rng.shuffle(ts)
    m=embedding.get_model(); tok=m._embedder._tokenizer
    if cap==onnx_embedding.MAX_TOKENS and len(sys.argv)>2:
        tok.no_truncation(); L=sorted(len(e.ids) for e in tok.encode_batch(t)); tok.enable_truncation(max_length=cap)
        print("tokens p50",L[len(L)//2],"p99",L[int(.99*len(L))],"max",L[-1],"over 512",sum(x>512 for x in L),"over 1024",sum(x>1024 for x in L),"over 2048",sum(x>2048 for x in L),"of",len(L),flush=True)
    t0=time.time(); V=[]
    for x in ts: V+=await embedding.embed_documents(m,[x])
    np.save(f"{S}/out/cap_{cap}.npy",np.array(V,dtype=np.float32))
    print("cap",cap,"seconds",round(time.time()-t0,1),"peak GB",round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,2),flush=True)
asyncio.run(main())
