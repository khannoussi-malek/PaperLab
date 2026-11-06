"""Asks a free router model for a hypothetical passage and for technical terms, per question; saved so a rerun skips them.
argv: dev|hold model. Prints counts only."""
import asyncio, json, os, sys, yaml, httpx
S = os.environ["S"]; KEY = os.environ["OMNI_KEY"]; SET = sys.argv[1]; MODEL = sys.argv[2]; OUT = f"{S}/out/rewrites_{SET}.json"
path = f"{S}/q/{SET}.yaml"; Q = yaml.safe_load(open(path)); Q = Q["questions"] if isinstance(Q, dict) else Q
HYDE = "Write 3 sentences as they would appear in a drug regulatory document or label, stating the answer to this question. If you do not know the facts, invent plausible ones: the wording matters, not the truth. Reply with the sentences only.\n\nQuestion: "
TERMS = "List the technical terms, abbreviations and synonyms a drug regulatory document would use for the concepts in this question, for a keyword search. Reply with at most 12 terms separated by commas, nothing else.\n\nQuestion: "
done = json.load(open(OUT)) if os.path.exists(OUT) else {}


async def ask(h, prompt):
    for wait in (0, 5, 30, 60):
        await asyncio.sleep(wait)
        try:
            r = await h.post("http://127.0.0.1:20128/v1/chat/completions", headers={"Authorization": f"Bearer {KEY}"}, json={"model": MODEL, "stream": False, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]})
            if r.status_code == 200:
                c = r.json()["choices"][0]["message"].get("content")
                if c: return c.strip(), r.json().get("model")
        except (httpx.HTTPError, KeyError, ValueError): pass
    return None, None


async def main():
    models = {}
    async with httpx.AsyncClient(timeout=90) as h:
        for q in Q:
            t = q["question"]
            if t in done and done[t].get("hyde") and done[t].get("terms"): continue
            a, m1 = await ask(h, HYDE + t); b, m2 = await ask(h, TERMS + t)
            done[t] = dict(hyde=a, terms=b); models[m1] = models.get(m1, 0) + 1; models[m2] = models.get(m2, 0) + 1
            json.dump(done, open(OUT, "w"))
    print(SET, "have", sum(1 for v in done.values() if v.get("hyde") and v.get("terms")), "of", len(Q), "models", models, flush=True)


asyncio.run(main())
