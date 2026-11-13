---
slug: check-validation
label: Check the validation
description: Where the ground truth came from and whether it holds. Criteria drawn from the community LLM reporting guidelines (llm-guidelines.org)
scope: both
version: 1
---
Judge where the ground truth in the paper or papers you were given came from, and whether it can be trusted. Go through each paper in turn, and say where they differ.

For each point, say what the paper reports, or say plainly that it doesn't report it.

- Source: where do the reference labels, scores or "correct answers" come from? An existing dataset, the authors, recruited annotators, experts, or a model?
- If people judged: how many, with what background, how they were trained or instructed, and whether they worked independently.
- Agreement: which agreement statistic is reported (for example Cohen's or Fleiss' kappa, Krippendorff's alpha), on how much of the data, and what value. A percentage of agreement alone says little.
- Disagreements: how were they settled? Discussion, majority vote, a senior judge?
- Construct: is the thing being judged defined, and are the instructions or rubric given to judges shared?
- If a model judged in place of people: is the substitution argued for, and checked against human judgement on a sample? How closely did they agree?

A missing detail is a gap in the reporting, not misconduct. Say what a reader would need to see to trust the labels. If a paper has no ground truth to validate (for example a purely formal result), say so and stop for that paper.

End with how much weight the results can bear, given what the validation shows.
