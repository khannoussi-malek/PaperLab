// M8.5: a question that reads like one for every paper gets a hint to switch Ask each paper on. No model call: the
// reader decides when to pay one call per paper.
const PER_PAPER = /\b(each|every|compare|comparing|across|which (papers|studies|of these)|all (the|these) (papers|studies))\b/i

export const looksPerPaper = (question: string) => PER_PAPER.test(question)
