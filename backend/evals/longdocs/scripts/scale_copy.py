"""Copies the 562 test papers five times (new ids, title 'copyN_'), chunks and vectors included, for speed only. Throwaway DB only."""
import asyncio, os, time
assert "55434/passrule" in os.environ["DATABASE_URL"]
from sqlalchemy import text
from app.db import SessionLocal
async def main():
    async with SessionLocal() as s:
        cols=[r[0] for r in (await s.execute(text("select column_name from information_schema.columns where table_name='papers' order by ordinal_position"))).all()]
        orig=[r[0] for r in (await s.execute(text("select id from papers where title like '%.pdf' and status='ready' and title not like 'copy%'"))).all()]
    print("papers",len(orig),flush=True)
    other=", ".join(c for c in cols if c not in ("id","title"))
    for n in range(2,6):
        t=time.time()
        async with SessionLocal() as s:
            await s.execute(text("create temp table m on commit drop as select id as old, gen_random_uuid() as new from papers where id = any(:ids)"),{"ids":orig})
            await s.execute(text(f"insert into papers (id, title, {other}) select m.new, 'copy{n}_' || p.title, {other} from papers p join m on m.old = p.id"))
            await s.execute(text("insert into chunks (id, paper_id, ordinal, page, bbox, section_title, text, embedding, embed_model, strategy_ver) select gen_random_uuid(), m.new, c.ordinal, c.page, c.bbox, c.section_title, c.text, c.embedding, c.embed_model, c.strategy_ver from chunks c join m on m.old = c.paper_id"))
            await s.commit()
        async with SessionLocal() as s: total=await s.scalar(text("select count(*) from chunks"))
        print("copy",n,"chunks now",total,"seconds",round(time.time()-t),flush=True)
    print("SCALE_COPY_DONE",flush=True)
asyncio.run(main())
