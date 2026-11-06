"""Real FDA approval reviews and EMA assessment reports for a true-length test. One at a time, politely. A rerun skips what's there."""
import json, os, time, urllib.request, urllib.error
B = os.path.expanduser("~/.cache/paperlab-bench"); OUT = f"{B}/pdfs"; LOG = f"{B}/out/fetch.jsonl"; UA = "PaperLab-benchmark/1.0"
FDA = {"apixaban": ("2012", "202155"), "rivaroxaban": ("2011", "022406"), "dabigatran": ("2010", "022512"), "edoxaban": ("2015", "206316"), "ticagrelor": ("2011", "022433"),
       "semaglutide": ("2017", "209637"), "semaglutide_oral": ("2019", "213051"), "liraglutide": ("2010", "022341"), "empagliflozin": ("2014", "204629"), "dapagliflozin": ("2014", "202293"),
       "canagliflozin": ("2013", "204042"), "ertugliflozin": ("2017", "209803"), "sacubitril": ("2015", "207620"), "tirzepatide": ("2022", "215866"), "vorapaxar": ("2014", "204886"), "prasugrel": ("2009", "022307")}
KINDS = ["MedR", "StatR", "ClinPharmR", "PharmR", "ChemR", "MultidisciplineR", "MultiDisciplineR", "SumR", "RiskR", "CrossR", "OtherR"]
EMA = ["eliquis", "xarelto", "pradaxa", "lixiana", "brilique", "ozempic", "rybelsus", "victoza", "wegovy", "jardiance", "forxiga", "invokana", "steglatro", "entresto", "mounjaro", "trulicity", "efient", "saxenda", "bydureon", "ozempic", "keytruda", "opdivo", "humira", "enbrel", "stelara", "dupixent", "repatha", "praluent", "leqvio", "verzenios", "kisqali", "ibrance", "tagrisso", "lynparza", "imbruvica", "venclyxto", "xtandi", "zytiga", "comirnaty", "spikevax"]
def get(url, path):
    if os.path.exists(path): return "have", os.path.getsize(path)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if "pdf" not in r.headers.get("content-type", ""): return "notpdf", 0
            data = r.read()
        open(path, "wb").write(data); return "ok", len(data)
    except urllib.error.HTTPError as e: return f"http{e.code}", 0
    except Exception as e: return type(e).__name__, 0
items = [(f"fda_{d}_{k}", f"https://www.accessdata.fda.gov/drugsatfda_docs/nda/{y}/{n}Orig1s000{k}.pdf") for d, (y, n) in FDA.items() for k in KINDS]
items += [(f"ema_{n}_assess", f"https://www.ema.europa.eu/en/documents/assessment-report/{n}-epar-public-assessment-report_en.pdf") for n in dict.fromkeys(EMA)]
items += [(f"ema_{n}_label", f"https://www.ema.europa.eu/en/documents/product-information/{n}-epar-product-information_en.pdf") for n in dict.fromkeys(EMA)]
blocked = 0
for name, url in items:
    st, size = get(url, f"{OUT}/{name}.pdf")
    open(LOG, "a").write(json.dumps(dict(name=name, url=url, status=st, size=size)) + "\n")
    blocked = blocked + 1 if st in ("http403", "http429") else 0
    if blocked >= 8: print("BLOCKED", name, flush=True); break
    if st != "have": time.sleep(1.5)
print("FETCH_DONE", flush=True)
