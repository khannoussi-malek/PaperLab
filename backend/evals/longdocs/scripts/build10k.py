"""One file of at least 10,000 pages from the real documents, in a seeded random order, and pages sampled for the question writer."""
import json, os, random, pymupdf
B=os.environ["S"]; rows=json.load(open(f"{B}/out/pdfs.json")); rng=random.Random(20261105)
use=[r for r in rows if r.get("good",0)>=.5]; out_docs=[r for r in rows if r.get("good",0)<.5]; rng.shuffle(use)
out=pymupdf.open(); spans=[]; small=None
for r in use:
    if out.page_count>=10000: break
    d=pymupdf.open(f"{B}/pdfs/{r['f']}"); start=out.page_count+1; out.insert_pdf(d); spans.append(dict(file=r["f"],start=start,end=out.page_count)); d.close()
os.makedirs(f"{B}/pass",exist_ok=True); out.save(f"{B}/pass/fixture.pdf",garbage=1)
smalls=[r for r in use if 8<=r["pages"]<=15 and r["f"] not in {s["file"] for s in spans}] or [r for r in use if r["pages"]<=40 and r["f"] not in {s["file"] for s in spans}]
json.dump(dict(rows=spans,small=f"{B}/pdfs/{smalls[0]['f']}" if smalls else None,pages=out.page_count,left_out=[r["f"] for r in out_docs]),open(f"{B}/pass/fixture.json","w"))
print("documents",len(spans),"pages",out.page_count,"MB",round(os.path.getsize(f"{B}/pass/fixture.pdf")/1e6),"left out",len(out_docs),sum(r.get("pages",0) for r in out_docs),"small",smalls[0]["f"] if smalls else None)
# Pages for the writer, chosen by the script, not by a search. Tables are pages dense in digits.
d=pymupdf.open(f"{B}/pass/fixture.pdf"); text=[];tab=[]
for s in spans:
    for p in range(s["start"],s["end"]+1):
        t=d[p-1].get_text()
        if 700<=len(t)<=5000:
            (tab if sum(c.isdigit() for c in t)/len(t)>.12 else text).append((s["file"],p,t))
rng.shuffle(text); rng.shuffle(tab)
pick=text[:80]+tab[:35]; rng.shuffle(pick); os.makedirs(f"{B}/q",exist_ok=True)
for i in range(0,len(pick),30):
    with open(f"{B}/q/pages_{i//30+1:02d}.txt","w") as f:
        for file,p,t in pick[i:i+30]: f.write(f"\n===== doc={file} joined_page={p} source_page={p-next(s['start'] for s in spans if s['file']==file)+1} kind_hint={'table' if (file,p,t) in tab[:35] else 'text'} =====\n{t}\n")
print("sampled",len(pick),"chars",sum(len(x[2]) for x in pick),"text pool",len(text),"table pool",len(tab)); print("docs by family",{k:sum(1 for s in spans if s['file'].startswith(k)) for k in("fda","ema")})
