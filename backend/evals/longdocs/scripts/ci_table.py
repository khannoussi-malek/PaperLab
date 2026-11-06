"""M6: one table of the main paired contrasts on every sealed set: gained, lost, exact McNemar p, paired bootstrap 95% CI of the difference (points)."""
import json, math, random, os
B=os.path.expanduser("~/.cache/paperlab-bench")
def mcn(b,c):
    n=b+c; return 1.0 if n==0 else min(1.0,2*sum(math.comb(n,i) for i in range(min(b,c)+1))/2**n)
def boot(x,y,ids,R=10000,seed=7):
    r=random.Random(seed); d=sorted((sum(y[i] for i in s)-sum(x[i] for i in s))/len(s) for s in ([r.choice(ids) for _ in ids] for _ in range(R)))
    return d[int(.025*R)],d[int(.975*R)]
def L(p):
    d=json.load(open(B+"/"+p)); return {m:{i:(v["ok"] if isinstance(v,dict) else v) for i,v in d[m].items()} for m in d}
s1=L("out/detail5_sealed_A_V_B_K_BUD30_K15B75.json"); s2=L("out/detail5_sealed2_A_V_B_K.json")
l1=L("out/bench6_sealed_T_H8_HB_D10.json"); l2=L("out/bench6_sealed2_T_H8_HB_D10.json")
se=L("secr/out/detail5_sealed_A_V_B_K.json"); sl=L("secr/out/bench6_sealed_T_H8_HB_D10.json")
C=[("Long file","S2","V","B",s2),("Long file","S2","A","B",s2),("Long file","S2","B","K",s2),("Long file","S1","V","B",s1),("Long file","S1","A","B",s1),("Long file","S1","B","K",s1),
   ("Library","S2","HB","D10",l2),("Library","S2","T","D10",l2),("Library","S1","HB","D10",l1),("Library","S1","T","D10",l1),
   ("SE file","SE","V","B",se),("SE file","SE","A","B",se),("SE library","SE","HB","D10",sl),("SE library","SE","T","D10",sl)]
for coll,st,a,b,d in C:
    x,y=d[a],d[b]; ids=sorted(set(x)&set(y)); g=sum(y[i] and not x[i] for i in ids); l=sum(x[i] and not y[i] for i in ids); lo,hi=boot(x,y,ids)
    print(f"{coll}|{st}|{a}->{b}|{len(ids)}|{sum(x[i] for i in ids)}|{sum(y[i] for i in ids)}|+{g} -{l}|{mcn(g,l):.3f}|{100*lo:+.1f} to {100*hi:+.1f}")
