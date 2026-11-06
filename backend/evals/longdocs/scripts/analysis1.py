"""Round 1 review numbers from saved per-question results: CIs, Holm, per kind, no-drug-named, dropped, answer-text check."""
import json, math, random, re, collections, yaml, os
B=os.path.expanduser("~/.cache/paperlab-bench"); O=B+"/out"
Q={q["id"]:q for q in yaml.safe_load(open(B+"/q/sealed.yaml"))}
def drug(q): return q["doc"].split("_")[1].lower()
def named(q): return drug(q) in q["question"].lower()
def wilson(k,n,z=1.96):
    if n==0: return (0,0)
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n)); return ((c-h)/d,(c+h)/d)
def mcn(b,c):
    n=b+c
    return 1.0 if n==0 else min(1.0,2*sum(math.comb(n,i) for i in range(min(b,c)+1))/2**n)
def boot(x,y,ids,R=10000,seed=7):
    r=random.Random(seed); d=[]
    for _ in range(R):
        s=[r.choice(ids) for _ in ids]; d.append((sum(y[i] for i in s)-sum(x[i] for i in s))/len(s))
    d.sort(); return d[int(.025*R)],d[int(.975*R)]
d5=json.load(open(O+"/bench5_sealed_A_V_B_BUD30_K15B75.json")); cap=json.load(open(O+"/bench5_sealed_B.json"))["B"]
d6=json.load(open(O+"/bench6_sealed_T_H8_HB_D10.json"))
def ans(f):
    by=collections.defaultdict(dict); txt=collections.defaultdict(dict); mod=collections.defaultdict(dict)
    for r in map(json.loads,open(O+"/"+f)): by[r["cfg"]][r["id"]]=r["right"]; txt[r["cfg"]][r["id"]]=r["answer"]; mod[r["cfg"]][r["id"]]=r.get("model")
    return by,txt,mod
ca,ct,cm=ans("answers_sealed.jsonl"); la,lt,lm=ans("local_sealed.jsonl")
C=[("long: A top8 -> B fused",d5["A"],d5["B"]),("long: V vectors@24k -> B fused [confirmatory-type]",d5["V"],d5["B"]),("long: B -> 30k",d5["B"],d5["BUD30"]),("long: B -> k1 1.5 b .75",d5["B"],d5["K15B75"]),("long: B -> 1,024 limit",d5["B"],cap),
   ("many: today -> docs first",d6["T"],d6["D10"]),("many: HB fused all -> docs first [confirmatory-type]",d6["HB"],d6["D10"]),("many: today -> switch on",d6["T"],d6["H8"]),
   ("cloud answers: A -> B",ca["A"],ca["B"]),("cloud answers: B -> L reorder",ca["B"],ca["L"]),("local answers: A -> B",la["A"],la["B"])]
rows=[]
for name,x,y in C:
    ids=sorted(set(x)&set(y)); g=sum(y[i] and not x[i] for i in ids); l=sum(x[i] and not y[i] for i in ids); n=len(ids)
    kx,ky=sum(x[i] for i in ids),sum(y[i] for i in ids); rows.append([name,n,kx,ky,g,l,mcn(g,l),boot(x,y,ids),wilson(kx,n),wilson(ky,n)])
m=len(rows); order=sorted(range(m),key=lambda i:rows[i][6]); adj=[0]*m; run=0
for rank,i in enumerate(order): run=max(run,min(1,(m-rank)*rows[i][6])); adj[i]=run
print("=== sealed contrasts (n, before, after, +, -, exact McNemar p, Holm p, paired diff 95% bootstrap CI, Wilson CIs)")
for r,a in zip(rows,adj): print(f"{r[0]:52} n{r[1]} {r[2]}->{r[3]} +{r[4]} -{r[5]} p={r[6]:.4f} holm={a:.4f} diff CI [{r[7][0]:+.3f},{r[7][1]:+.3f}] before [{r[8][0]:.2f},{r[8][1]:.2f}] after [{r[9][0]:.2f},{r[9][1]:.2f}]")
print("MDE exact McNemar alpha .05: b,c=0 needs b>=6 (p=%.3f; b=5 p=%.3f); one opposite: b>=8 (p=%.3f)"%(mcn(6,0),mcn(5,0),mcn(8,1)))
print("=== per kind, long file sealed")
for meth in ["A","V","B","BUD30","K15B75"]:
    c=collections.Counter(); t=collections.Counter()
    for i,v in d5[meth].items(): t[Q[i]["kind"]]+=1; c[Q[i]["kind"]]+=v
    print(meth,{k:f"{c[k]}/{t[k]}" for k in sorted(t)})
for meth in ["T","H8","HB","D10"]:
    c=collections.Counter(); t=collections.Counter()
    for i,v in d6[meth].items(): t[Q[i]["kind"]]+=1; c[Q[i]["kind"]]+=v
    print("many",meth,{k:f"{c[k]}/{t[k]}" for k in sorted(t)})
def sub(name,x,y,f):
    ids=[i for i in x if i in y and f(Q[i])]; g=sum(y[i] and not x[i] for i in ids); l=sum(x[i] and not y[i] for i in ids)
    print(f"{name:45} n{len(ids)} {sum(x[i] for i in ids)}->{sum(y[i] for i in ids)} +{g} -{l} p={mcn(g,l):.3f}")
print("=== subsets")
sub("long V->B reworded",d5["V"],d5["B"],lambda q:q["kind"]=="reworded")
sub("long V->B drug not named",d5["V"],d5["B"],lambda q:not named(q))
sub("long V->B drug named",d5["V"],d5["B"],lambda q:named(q))
sub("long A->B drug not named",d5["A"],d5["B"],lambda q:not named(q))
sub("many HB->D10 drug not named",d6["HB"],d6["D10"],lambda q:not named(q))
sub("many T->D10 drug not named",d6["T"],d6["D10"],lambda q:not named(q))
print("drug named in",sum(named(q) for q in Q.values()),"of",len(Q),collections.Counter(q["kind"] for q in Q.values() if named(q)))
print("=== dropped: long file",sorted(set(Q)-set(d5["B"])),"many",sorted(set(Q)-set(d6["T"])),"answers scored on",len(ca["B"]))
# answer-text check, rule fixed in the log before this ran
STOP=set("with from that this were been have than which their there these those after before during between under over".split())
def normt(s):
    s=s.lower()
    for ch in "‐‑‒–—−": s=s.replace(ch,"-")
    s=s.replace("×","x").replace(" "," ").replace(" "," ").replace(" "," ")
    s=re.sub(r"(?<=\d),(?=\d{3}\b)","",s); return " ".join(s.split())
NUM=re.compile(r"-?\d+(?:\.\d+)?")
def smet(w,a):
    w=normt(w)
    if re.search(r"\d",w):
        need=collections.Counter(NUM.findall(w)); have=collections.Counter(NUM.findall(a)); return all(have[k]>=v for k,v in need.items())
    if w in a: return True
    ws=[x for x in re.findall(r"[a-z]{4,}",w) if x not in STOP]; return bool(ws) and all(x in a for x in ws)
def qmet(q,a):
    a=normt(a or ""); return all(any(all(smet(w,a) for w in alt["all_of"]) for alt in need) for need in q["needs"])
print("=== answer-text check (rule fixed before scoring)")
for lab,by,txt in [("cloud",ca,ct),("local",la,lt)]:
    for c in sorted(by):
        ids=[i for i in by[c] if i in Q]; t=sum(qmet(Q[i],txt[c][i]) for i in ids); both=sum(qmet(Q[i],txt[c][i]) and by[c][i] for i in ids)
        print(f"{lab} {c}: text {t}/{len(ids)}  text+citation {both}/{len(ids)}  citation {sum(by[c][i] for i in ids)}/{len(ids)}")
    if "A" in by:
        x={i:qmet(Q[i],txt["A"][i]) for i in by["A"] if i in Q}; y={i:qmet(Q[i],txt["B"][i]) for i in by["B"] if i in Q}
        ids=sorted(set(x)&set(y)); g=sum(y[i] and not x[i] for i in ids); l=sum(x[i] and not y[i] for i in ids); print(f"{lab} text A->B +{g} -{l} p={mcn(g,l):.4f}")
print("=== cloud answer models per method", {c:dict(collections.Counter(cm[c].values())) for c in cm})
