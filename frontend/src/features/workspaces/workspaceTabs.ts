import type { WorkspaceTab } from '@/lib/route'

export type TabMeta = {
  value: WorkspaceTab
  group: 'papers' | 'review'
  label: string
  step?: 1 | 2 | 3 | 4 | 5
  stepLine: string
}

export const GROUP_LABELS = { papers: 'Your papers', review: 'Systematic review' } as const

/** Display order. Tab labels carry their step number; `tabAriaLabel` keeps the plain name first. */
export const WORKSPACE_TABS: readonly TabMeta[] = [
  { value: 'papers', group: 'papers', label: 'Papers', stepLine: 'The papers in this workspace. Add them from your library, upload PDFs, or find one by DOI or title.' },
  { value: 'notes', group: 'papers', label: 'Notes', stepLine: 'Every note on these papers, grouped by paper. Highlight a passage in the reader to add one.' },
  { value: 'chat', group: 'papers', label: 'Chat', stepLine: 'Ask questions across these papers and your notes. Answers cite the passages they use.' },
  { value: 'evidence', group: 'papers', label: 'Evidence', stepLine: "One row per paper. AI pulls out each study's design, sample, findings and limitations, with quotes you can check." },
  { value: 'search', group: 'review', label: 'Search & screen', step: 1, stepLine: 'Step 1 of 5. Search paper sources, then mark each result relevant or not from its title and abstract.' },
  { value: 'acquisition', group: 'review', label: 'Get PDFs', step: 2, stepLine: 'Step 2 of 5. Relevant papers with no free PDF found. Get each one yourself and upload it.' },
  { value: 'screening', group: 'review', label: 'Full-text review', step: 3, stepLine: 'Step 3 of 5. Read each imported paper and decide whether it meets your criteria.' },
  { value: 'reading', group: 'review', label: 'Reading list', step: 4, stepLine: 'Step 4 of 5. The papers you included, in reading order.' },
  { value: 'prisma', group: 'review', label: 'PRISMA report', step: 5, stepLine: 'Step 5 of 5. The counts at each step, in the PRISMA 2020 flow, ready for your methods section.' },
]

const COUNT_NOUN: Partial<Record<WorkspaceTab, string>> = {
  papers: 'papers',
  notes: 'notes',
  acquisition: 'to fetch',
  screening: 'to review',
}

/** "Get PDFs, step 2 of 5, 12 to fetch": the plain name first, then the step, then the count when there is one. */
export function tabAriaLabel(meta: TabMeta, count?: number): string {
  const noun = COUNT_NOUN[meta.value]
  const parts = [meta.label]
  if (meta.step) parts.push(`step ${meta.step} of 5`)
  if (count && noun) parts.push(`${count.toLocaleString('en')} ${noun}`)
  return parts.join(', ')
}
