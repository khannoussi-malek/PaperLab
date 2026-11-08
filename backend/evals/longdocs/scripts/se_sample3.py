"""Fresh SE pages for a blind writer (round R3): none sampled before, seeded 20261110. Tables are digit-dense pages."""
import glob, os, random, re, pymupdf
S=os.path.expanduser("~/.cache/paperlab-bench/secr")
used=set()
for f in glob.glob(f"{S}/q/pages_*.txt"):
    for doc,p in re.findall(r"doc=(\S+) .*?page=(\d+)",open(f).read()): used.add((doc,int(p)))
title={l.split("\t")[0]:l.rstrip("\n").split("\t")[3] for l in open(f"{S}/papers.tsv")}
rng=random.Random(20261110); text=[]; tab=[]
for f in sorted(glob.glob(f"{S}/pdfs/*.pdf")):
    doc=os.path.basename(f)
    try: d=pymupdf.open(f)
    except Exception: continue
    for p in range(1,d.page_count+1):
        if (doc,p) in used: continue
        t=d[p-1].get_text()
        if 700<=len(t)<=5000: (tab if sum(c.isdigit() for c in t)/len(t)>.12 else text).append((doc,p,t))
    d.close()
rng.shuffle(text); rng.shuffle(tab); tb=set((x[0],x[1]) for x in tab[:35]); pick=text[:80]+tab[:35]; rng.shuffle(pick)
for i in range(0,len(pick),30):
    with open(f"{S}/q3/pages_{i//30+1:02d}.txt","w") as out:
        for doc,p,t in pick[i:i+30]: out.write(f'\n===== doc={doc} title="{title.get(doc[:-4],"")}" page={p} kind_hint={"table" if (doc,p) in tb else "text"} =====\n{t}\n')
print("excluded",len(used),"pages",len(pick),"docs",len({x[0] for x in pick}),"files",(len(pick)+29)//30)
