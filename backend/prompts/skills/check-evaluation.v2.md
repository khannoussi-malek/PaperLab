---
slug: check-evaluation
label: Check the evaluation
description: Whether the numbers measure what they claim to. Criteria drawn from the community LLM reporting guidelines (llm-guidelines.org)
scope: both
version: 2
lens: critical
---
Judge whether the evaluation in the paper or papers you were given supports their claims. Go through each paper in turn, and say where they differ.

For each point below, say what the paper reports, or say plainly that it doesn't report it.

- What is measured, and is it defined well enough to be measured? A claim about "quality" or "usefulness" needs an operational definition.
- Why these metrics? A metric chosen because earlier work used it is a habit, not a justification. Note when the metric could reward the wrong thing.
- Baselines: are they recent, strong and tuned with similar care? A new method tuned hard against a default baseline is not a fair comparison.
- Tasks and data: how were they chosen, and do they match the claim's scope? Note any sign the test data overlaps what a model was trained on.
- Runs and spread: one run or several? Is variation (standard deviation, confidence intervals) reported?
- Comparisons: are differences backed by a statistical test or an effect size, or are averages simply placed side by side?
- Errors: is there any analysis of where and why the method fails?

A missing detail is a gap in the reporting, not proof that something was done wrongly. Say what a reader would need to see. If a paper has no empirical evaluation, say so and stop for that paper.

End with a short verdict per paper: which claims the evaluation supports, which it supports only partly, and the one change that would most strengthen it.
