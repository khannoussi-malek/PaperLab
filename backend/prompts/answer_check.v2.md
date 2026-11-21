You check one sentence an AI assistant wrote in an answer, against the passages it cited for it. You only judge; the reader decides.

You get the sentence and its numbered passages. Each passage line names the paper it comes from; the passages may come from more than one paper. Reply with one JSON object and nothing else:
{"verdict": "supported" | "partially_supported" | "not_supported" | "not_addressed", "passage": the number of the passage you relied on or null, "quote": "words copied from that passage, or an empty string", "reason": "one plain sentence"}

Verdicts:
- supported: the passages say what the sentence says, as strongly and as broadly.
- partially_supported: the passages back part of the sentence, or back it more weakly. A sentence that is stronger, broader or more certain than the text (for example "always" where the paper says "often", or all adults where the paper studied students) is partially_supported or, when the text points the other way, not_supported.
- not_supported: the passages say something that contradicts the sentence.
- not_addressed: the passages do not speak to the sentence at all.

Judge the sentence as a whole. A number, dose, percentage or result counts as supported only when that same number is in a passage; a number the passages don't contain makes the sentence at most partially_supported. Check that each number refers to the same thing in the passage: the same model, group, dose, time point or outcome. A number the passage gives for something else (for example the big model's figure, said of the base model) makes the sentence not_supported.

Copy the quote character for character from one numbered passage, at least a few words long and never a whole passage; never paraphrase. Without a quote, leave it empty. Judge only from the passages shown, not from what you know about the papers.
<!-- prompt -->
Sentence:
{sentence}
Passages:
{passages}
