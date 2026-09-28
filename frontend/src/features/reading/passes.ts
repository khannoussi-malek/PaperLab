export type Triage = 'keep' | 'later' | 'drop'
export const LEVELS = [
  { value: 0, label: 'None yet' }, { value: 1, label: 'Pass 1' }, { value: 2, label: 'Pass 2' }, { value: 3, label: 'Pass 3' },
] as const
export const TRIAGES = [
  { value: 'keep', label: 'Keep', chip: 'Keep' },
  { value: 'later', label: 'Later', chip: 'Later' },
  { value: 'drop', label: 'Drop', chip: 'Dropped' },
] as const
export const UNDECIDED_LABEL = 'Not decided'

/** One row of PASSES. M22 adds `noteKind` (its exit-test note kind) to this type. */
export type Pass = {
  pass: 1 | 2 | 3
  heading: string
  steps: string[]
  doneWhen: string
  fiveCs?: string[] // pass 1 only: the five questions under "Done when"
  then?: string // pass 1 only: the decision line
  references: boolean // shows Open References
}

export const PASSES: readonly Pass[] = [
  {
    pass: 1,
    heading: 'Pass 1 · 5–10 minutes',
    steps: [
      'Read the title, the abstract and the introduction.',
      'Read the section and sub-section headings, and nothing else.',
      'Read the conclusion.',
      'Glance over the references and note the ones you’ve already read.',
    ],
    doneWhen: 'Done when you can answer the five Cs:',
    fiveCs: [
      'Category: what type of paper is it?',
      'Context: which papers is it related to, and what theory does it build on?',
      'Correctness: do its assumptions look valid?',
      'Contributions: what are its main contributions?',
      'Clarity: is it well written?',
    ],
    then: 'Then decide: Keep, Later or Drop.',
    references: true,
  },
  {
    pass: 2,
    heading: 'Pass 2 · about an hour',
    steps: [
      'Read it with care, but skip the proofs.',
      'Check the figures: are the axes labelled, are there error bars, do the results support the conclusions?',
      'Jot down the key points.',
      'Mark the references you haven’t read To read.',
    ],
    doneWhen: 'Done when you can summarise its main thrust, with the evidence for it, to someone else.',
    references: true,
  },
  {
    pass: 3,
    heading: 'Pass 3 · 1–5 hours',
    steps: [
      'Re-create the work in your head: make the authors’ assumptions and rebuild it, then compare yours with theirs.',
      'Challenge every assumption.',
      'Note ideas for future work.',
    ],
    doneWhen: 'Done when you can rebuild its structure from memory and name its strong and weak points, its implicit assumptions and its missing citations.',
    references: false,
  },
]

/** The next pass to work towards, or null once every pass is finished. */
export const nextPass = (level: number): Pass | null => PASSES[level] ?? null

/** The library/toolbar chip's text: null at the normal state (pass 0, undecided), so nothing shows. */
export function readingChip(pass: number, triage: Triage | null): string | null {
  const level = pass > 0 ? `Pass ${pass}` : null
  const decision = triage ? TRIAGES.find((t) => t.value === triage)!.chip : null
  return level && decision ? `${level} · ${decision}` : level ?? decision
}
