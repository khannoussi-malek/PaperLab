import type { PrismaExportOut } from '@/api/client'
import type { GlossaryKey } from '@/features/workspaces/glossary'
import { reasonLabel } from './hitReview'

export type StageKey =
  | 'identified'
  | 'duplicates_removed'
  | 'stage1_screened'
  | 'stage1_excluded'
  | 'sought'
  | 'not_retrieved'
  | 'stage2_assessed'
  | 'stage2_excluded'
  | 'included'

// PRISMA's own flow-diagram phases, so the funnel reads as the methodology a systematic-review author already
// knows, not an arbitrary 9-row table.
export type Row = [StageKey, string, GlossaryKey | null]
export const PHASES: [string, GlossaryKey | null, Row[]][] = [
  [
    'Identification',
    null,
    [
      ['identified', 'Identified', 'identified'],
      ['duplicates_removed', 'Duplicates removed', 'duplicatesRemoved'],
    ],
  ],
  [
    'Screening',
    null,
    [
      ['stage1_screened', 'Screened on title & abstract', 'titleAbstract'],
      ['stage1_excluded', 'Excluded on title & abstract', 'titleAbstract'],
    ],
  ],
  [
    'Eligibility',
    'eligibility',
    [
      ['sought', 'Reports sought', 'reportsSought'],
      ['not_retrieved', 'Not retrieved', 'notRetrieved'],
      ['stage2_assessed', 'Full texts assessed', 'fullText'],
      ['stage2_excluded', 'Excluded after full text', 'fullText'],
    ],
  ],
  ['Included', null, [['included', 'Included', null]]],
]

// A stage whose count has a reason breakdown (spec §13): reason -> count, straight off PrismaExportOut, no
// separate fetch.
export const REASON_FIELD: Partial<Record<StageKey, 'stage1_excluded_by_reason' | 'stage2_excluded_by_reason'>> = {
  stage1_excluded: 'stage1_excluded_by_reason',
  stage2_excluded: 'stage2_excluded_by_reason',
}

function boxes(data: PrismaExportOut) {
  return PHASES.flatMap(([phase, , rows]) =>
    rows.map(([key, label]) => {
      const field = REASON_FIELD[key]
      const reasons = Object.entries(field ? data[field] : {}).map(([r, n]) => `${reasonLabel(r)}: ${n}`)
      return { phase, label, count: data[key], reasons }
    }),
  )
}

/** One line per box, funnel order, labelled as on screen; reasons in parentheses. */
export function prismaText(data: PrismaExportOut, runLabel: string): string {
  const lines = boxes(data).map(({ label, count, reasons }) => `${label}: ${count}${reasons.length ? ` (${reasons.join(', ')})` : ''}`)
  return [`PRISMA flow: ${runLabel}`, ...lines].join('\n')
}

// Text fields starting with = + - @ get a leading ' so Excel doesn't run them as formulas; counts are numbers we wrote.
const q = (v: string | number) => {
  const t = typeof v === 'string' && /^[=+\-@\t\r]/.test(v) ? `'${v}` : String(v)
  return `"${t.replace(/"/g, '""')}"`
}

/** RFC 4180: every field quoted, inner quotes doubled. Header, a run row, then one row per box. */
export function prismaCsv(data: PrismaExportOut, runLabel: string): string {
  const rows = [
    ['stage', 'box', 'count', 'reasons'],
    ['Run', runLabel, '', ''],
    ...boxes(data).map((b) => [b.phase, b.label, b.count, b.reasons.join('; ')]),
  ]
  return rows.map((r) => r.map(q).join(',')).join('\n')
}
