---
slug: llm-reporting
label: Check LLM reporting
description: Whether a study that used language models could be repeated. Criteria drawn from the community LLM reporting guidelines (llm-guidelines.org)
scope: both
version: 2
lens: method
---
Judge whether someone could repeat the parts of the study done with language models, in the paper or papers you were given. Go through each paper in turn; with several, end with a short comparison of which ones could be repeated and which could not.

Only the method counts. Leave aside any use of a model to help write the paper itself: that is a matter for the venue's policy, not a method detail.

For each point, say what the paper reports, or say plainly that it doesn't report it.

- The exact model, its version or snapshot, and when it was run. "GPT-4" without a version or date is not enough to repeat a study.
- Configuration: temperature and other sampling settings, context length, any fine-tuning.
- Prompts: are they given in full, and how many examples did they include?
- What surrounds the model: retrieval, tools, agents, chained steps, filtering or post-processing of its output.
- Repeated runs: was each prompt run more than once, and is the variation between runs reported?
- Open alternative: if only a commercial model was used, was an open model tried alongside it, or is the choice explained?
- Shared material: are inputs, outputs or interaction logs made available?

If no language model is part of the method, say so and stop for that paper. A missing item is a reporting gap, not misconduct.

End with what a reader would need to ask the authors for to repeat the work.
