"""Fresh pages for two blind writers: none sampled before, seeded, spread over documents. Tables are digit-dense pages."""
import json, os, random, re, pymupdf
B=os.environ["S"]; F=json.load(open(f"{B}/pass/fixture.json")); spans=F["rows"]
used={int(m) for f in os.listdir(f"{B}/q") if f.startswith("pages_") for m in re.findall(r"joined_page=(\d+)",open(f"{B}/q/{f}").read())}
rng=random.Random(20261106); d=pymupdf.open(f"{B}/pass/fixture.pdf"); text=[];tab=[]
for s in spans:
    for p in range(s["start"],s["end"]+1):
        if p in used: continue
        t=d[p-1].get_text()
        if 700<=len(t)<=5000: (tab if sum(c.isdigit() for c in t)/len(t)>.12 else text).append((s["file"],p,t,s["start"]))
rng.shuffle(text); rng.shuffle(tab)
for part,(tx,tb) in enumerate([(text[:80],tab[:35]),(text[80:160],tab[35:70])],1):
    pick=tx+tb; rng.shuffle(pick); os.makedirs(f"{B}/q2/{part}",exist_ok=True)
    for i in range(0,len(pick),30):
        with open(f"{B}/q2/{part}/pages_{i//30+1:02d}.txt","w") as f:
            for file,p,t,st in pick[i:i+30]: f.write(f"\n===== doc={file} joined_page={p} source_page={p-st+1} kind_hint={'table' if (file,p,t,st) in tb else 'text'} =====\n{t}\n")
    print("set",part,"pages",len(pick),"chars",sum(len(x[2]) for x in pick),"docs",len({x[0] for x in pick}))
print("excluded",len(used))
