"""Real answers through the real chat.prepare and the real OllamaLLM (local), with a disk guard. A today, B branch, L branch with best first and second best last. Saves each; a rerun skips what's done. argv: models, cfgs, out."""
import asyncio, json, os, shutil, subprocess, sys, time, uuid, yaml, httpx
from app.providers.llm import OllamaLLM
from unittest.mock import patch
assert "55434/passrule" in os.environ["DATABASE_URL"]
from app.core import chat, retrieval
from app.db import SessionLocal
from app.providers.embedding import get_model
S=os.environ["S"]; MODELS=sys.argv[1].split(","); CFGS=sys.argv[2]; OUT=f"{S}/out/{sys.argv[3]}"; SET=sys.argv[4] if len(sys.argv)>4 else "sealed"
PID=uuid.UUID(open(f"{S}/pass/pid").read().strip()); F=json.load(open(f"{S}/pass/fixture.json")); SPAN={r["file"]:(r["start"],r["end"]) for r in F["rows"]}
Q=yaml.safe_load(open(f"{S}/q/{SET}.yaml")); norm=lambda s:" ".join(str(s).lower().split())
done={(r["cfg"],r["id"]) for r in map(json.loads,open(OUT))} if os.path.exists(OUT) else set(); resting={}
def met(need,chunks,spans):
    for span in spans:
        tx=[norm(c.text) for c in chunks if span[0]<=c.page<=span[1]]
        if any(all(any(norm(w) in x for x in tx) for w in a["all_of"]) for a in need): return True
    return False
class Busy(Exception): pass
from app.providers.llm import OLLAMA_NUM_CTX
async def ask(model,system,prompt):
    """The app's own Ollama request (think off, num_ctx), plus temperature 0 and a fixed seed for repeatability."""
    if shutil.disk_usage("/System/Volumes/Data").free<5e9:
        subprocess.run(["ollama","stop",model]); print("LOW_DISK",flush=True); sys.exit(3)
    body={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"stream":True,"think":False,"options":{"num_ctx":OLLAMA_NUM_CTX,"temperature":0,"seed":1}}
    t=time.time(); first=None; parts=[]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5)) as h, h.stream("POST","http://127.0.0.1:11434/api/chat",json=body) as r:
            async for line in r.aiter_lines():
                if not line: continue
                d=json.loads(line)
                if c:=d.get("message",{}).get("content"): first=first or time.time()-t; parts.append(c)
                if d.get("done"): break
    except Exception as e: return "",{"first":None,"err":f"{type(e).__name__}: {str(e)[:120]}"},model
    return "".join(parts),{"first":round(first or 0,1)},model
async def one(cfg,q,m,model):
    async with SessionLocal() as s:
        if cfg=="A":
            with patch.object(chat,"RETRIEVE_POOL",8),patch.object(retrieval,"LONG_PAPER_CHUNKS",10**9): p=await chat.prepare(s,PID,q["question"],embedder=m)
        elif cfg=="M":
            orig=chat.cut_to_budget
            with patch.object(chat,"cut_to_budget",lambda found: orig(found,12000)): p=await chat.prepare(s,PID,q["question"],embedder=m)
        else: p=await chat.prepare(s,PID,q["question"],embedder=m)
        src=p.sources; prompt=p.prompt
        if cfg=="L":
            src=list(p.sources[0::2])+list(reversed(p.sources[1::2])); paper=await chat.get_paper(s,PID); o=chat.format_context(paper,p.sources); assert o in prompt; prompt=prompt.replace(o,chat.format_context(paper,src))
        await s.rollback()
    t=time.time(); a,u,got=await ask(model,p.system,prompt); dt=time.time()-t
    cited=[src[i-1] for i in chat.parse_citations(a,len(src))]
    sp=[SPAN[q["doc"]]]+[v for v in SPAN.values() if q["kind"]=="multi"]
    given=all(met(n,src,sp) for n in q["needs"]); right=all(met(n,cited,sp) for n in q["needs"])
    open(OUT,"a").write(json.dumps(dict(cfg=cfg,id=q["id"],kind=q["kind"],model=got,given=given,right=right,n=len(src),s=round(dt,1),tok=None,first=u.get("first"),err=u.get("err"),answer=a))+"\n"); done.add((cfg,q["id"]))
    print(cfg,q["id"],got,"right",right,"given",given,flush=True); await asyncio.sleep(0)
async def main():
    m=get_model()
    for q in Q:
        for cfg in CFGS:
            while (cfg,q["id"]) not in done:
                now=time.time(); model=next((x for x in MODELS if resting.get(x,0)<=now),None)
                if model is None: await asyncio.sleep(max(min(resting.values())-now,5)); continue
                try: await one(cfg,q,m,model)
                except Busy as e: print("REST",model,e,flush=True); resting[model]=time.time()+600
    print("ANSWERS_DONE",flush=True)
asyncio.run(main())
