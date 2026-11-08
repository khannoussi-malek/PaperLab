"""SE4 pages for two blind writers: seed 20261111, none sampled before (old SE writer, SE3), two disjoint sets of 100 text + 45 table pages. Tables are digit-dense pages."""
import glob, os, random, re, pymupdf
S=os.path.expanduser("~/.cache/paperlab-bench/secr"); used=set()
for f in glob.glob(f"{S}/q/pages_*.txt")+glob.glob(f"{S}/q3/pages_*.txt"):
    for doc,p in re.findall(r"doc=(\S+) .*?page=(\d+)",open(f).read()): used.add((doc,int(p)))
title={l.split("\t")[0]:l.rstrip("\n").split("\t")[3] for l in open(f"{S}/papers.tsv")}
rng=random.Random(20261111); text=[]; tab=[]
for f in sorted(glob.glob(f"{S}/pdfs/*.pdf")):
    doc=os.path.basename(f)
    try: d=pymupdf.open(f)
    except Exception: continue
    for p in range(1,d.page_count+1):
        if (doc,p) in used: continue
        t=d[p-1].get_text()
        if 700<=len(t)<=5000: (tab if sum(c.isdigit() for c in t)/len(t)>.12 else text).append((doc,p,t))
    d.close()
rng.shuffle(text); rng.shuffle(tab)
for part,(tx,tb) in enumerate([(text[:100],tab[:45]),(text[100:200],tab[45:90])],1):
    tset={(x[0],x[1]) for x in tb}; pick=tx+tb; rng.shuffle(pick); os.makedirs(f"{S}/q4/{part}",exist_ok=True)
    for i in range(0,len(pick),30):
        with open(f"{S}/q4/{part}/pages_{i//30+1:02d}.txt","w") as out:
            for doc,p,t in pick[i:i+30]: out.write(f'\n===== doc={doc} title="{title.get(doc[:-4],"")}" page={p} kind_hint={"table" if (doc,p) in tset else "text"} =====\n{t}\n')
    print("set",part,"pages",len(pick),"docs",len({x[0] for x in pick}))
print("excluded",len(used))
