"""Pages and text per PDF, so scanned documents can be left out and counted."""
import glob, json, os, pymupdf, collections
B=os.path.expanduser("~/.cache/paperlab-bench"); rows=[]
for f in sorted(glob.glob(B+"/pdfs/*.pdf")):
    try: d=pymupdf.open(f)
    except Exception as e: rows.append(dict(f=os.path.basename(f),err=str(e)[:60])); continue
    n=d.page_count; step=max(1,n//40); chars=[len(d[i].get_text()) for i in range(0,n,step)]; good=sum(c>=200 for c in chars)/len(chars)
    rows.append(dict(f=os.path.basename(f),pages=n,good=round(good,2),med=sorted(chars)[len(chars)//2],mb=round(os.path.getsize(f)/1e6,1))); d.close()
json.dump(rows,open(B+"/out/pdfs.json","w"))
ok=[r for r in rows if r.get("good",0)>=.8]; bad=[r for r in rows if r not in ok]
print("files",len(rows),"pages",sum(r.get("pages",0) for r in rows),"| text ok",len(ok),"pages",sum(r["pages"] for r in ok),"| left out",len(bad),"pages",sum(r.get("pages",0) for r in bad))
fam=collections.Counter()
for r in ok: fam[r["f"].split("_")[0]+"_"+r["f"].rsplit("_",1)[1][:-4]]+=r["pages"]
print(dict(fam)); print("longest",[(r["f"],r["pages"]) for r in sorted(ok,key=lambda r:-r["pages"])[:10]]); print("left out",[(r["f"],r.get("pages"),r.get("good")) for r in bad][:30])
