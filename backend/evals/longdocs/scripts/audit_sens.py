"""Sealed results with all keys and without the keys Llama 3.3 70B flags (rule logged before the audit ran)."""
import json, math, os
B=os.path.expanduser("~/.cache/paperlab-bench"); O=B+"/out"
FLAG={x["id"] for x in map(json.loads,open(O+"/audit_llama.jsonl")) if x["verdict"] not in ("ok","no_verdict")}
def mcn(b,c):
    n=b+c; return 1.0 if n==0 else min(1.0,2*sum(math.comb(n,i) for i in range(min(b,c)+1))/2**n)
s1l=json.load(open(O+"/bench5_sealed_A_V_B_K_BUD30_K15B75.json")); s1m=json.load(open(O+"/bench6_sealed_T_H8_HB_D10.json"))
s2l=json.load(open(O+"/bench5_sealed2_A_V_B_K.json")); s2m=json.load(open(O+"/bench6_sealed2_T_H8_HB_D10.json"))
C=[("set1 long A->B",s1l,"A","B"),("set1 long V->B",s1l,"V","B"),("set1 many T->D10",s1m,"T","D10"),("set1 many HB->D10",s1m,"HB","D10"),
   ("set2 long A->B",s2l,"A","B"),("set2 long V->B [conf]",s2l,"V","B"),("set2 long B->K",s2l,"B","K"),("set2 many T->D10",s2m,"T","D10"),("set2 many HB->D10 [conf]",s2m,"HB","D10"),("set2 many T->H8",s2m,"T","H8")]
out=[]
for name,d,a,b in C:
    for tag,drop in (("all",set()),("noflag",FLAG)):
        ids=sorted(i for i in set(d[a])&set(d[b]) if i not in drop); x,y=d[a],d[b]
        g=sum(y[i] and not x[i] for i in ids); l=sum(x[i] and not y[i] for i in ids)
        r=dict(name=name,keys=tag,n=len(ids),before=sum(x[i] for i in ids),after=sum(y[i] for i in ids),gain=g,loss=l,p=round(mcn(g,l),4)); out.append(r)
        print(f"{name:26} {tag:6} n{r['n']} {r['before']}->{r['after']} +{g} -{l} p={r['p']}")
json.dump(dict(flagged=sorted(FLAG),rows=out),open(O+"/audit_sens.json","w"),indent=1)
