You read one research paper's passages and answer a question for this paper only.

- Use only the passages below, each labelled [P1], [P2] and so on. Never use what you know from elsewhere.
- Speak only for this paper. When the question names other documents (another label, a trial, a guideline), never say what they say: say what this paper says, as this paper.
- If the passages answer the question, reply with status "found", an answer of at most three sentences that begins with "This paper", and the labels of the passages that support it in "cites".
- If they don't answer it, reply with status "absent" and say in one sentence what the passages cover instead. A paper that doesn't address the question is a real finding: never stretch a passage to make it fit.
- Reply with only this JSON object, no other text:
{"status": "found" or "absent", "answer": "...", "cites": ["P1", ...]}
<!-- prompt -->
Paper: {paper}

Passages:

{passages}

Question, answered for this paper only: {question}
