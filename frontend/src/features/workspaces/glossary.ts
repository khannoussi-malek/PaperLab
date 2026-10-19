/** Plain-language explanations shown by <Term>. One place so wording stays consistent across the workspace tabs. */
export const GLOSSARY = {
  prisma: 'PRISMA 2020 is the standard flow diagram for reporting a systematic review: how many records you found, screened, excluded and included.',
  titleAbstract: 'First screening pass: decide from the title and abstract alone whether a result could be relevant.',
  fullText: 'Second screening pass: read the full paper and decide whether it meets your inclusion criteria.',
  eligibility: 'The full-text stage of PRISMA: papers checked against your inclusion criteria.',
  reportsSought: 'Relevant papers you tried to get the full text of.',
  notRetrieved: 'Relevant papers with no full text yet: no free PDF was found and none was uploaded. Papers saved without a PDF count here too, until their PDF arrives.',
  duplicatesRemoved: 'Records found more than once, across sources or runs, counted once.',
  identified: 'Every record your searches returned, across all runs, before duplicates are removed.',
  results: 'The papers a search returned, after duplicates are merged. Filters on this tab narrow what you see.',
  run: 'One search: its query, its year range and everything it found. Each Start makes a new run.',
  snowball: 'Citation search: adds the papers this one cites and the papers that cite it, as new results to screen.',
  preScreen: 'After a scheduled search, a local AI model suggests include or exclude for each new result. You still decide.',
  aiSuggestion: "The AI model's include or exclude call from the title and abstract, with its reasons. Accept turns it into your decision.",
  score: 'How well the AI thinks the result fits your criteria, from 1 (poor) to 5 (strong).',
  lowConfidence: "The AI wasn't sure. Read this one yourself.",
  quoteMismatch: "A quote the AI gave as a reason isn't in the abstract word for word, so check its reasoning.",
  nothingFound: 'The AI found no statement for this field in the paper.',
  leftOut: "Items the AI proposed without a quote from the paper to back them. They're hidden so nothing unsupported shows.",
  detailsSource: "Where PaperLab found this paper's title, authors and abstract when it was saved. Edit details changes them.",
  needsFullText: "Evidence cards are made from a paper's full text. This paper has no PDF yet, so there is no card to make.",
  notesUsed: "Chat sends your newest notes that fit in the model's context. Older notes beyond that aren't used for this answer.",
} as const

export type GlossaryKey = keyof typeof GLOSSARY
