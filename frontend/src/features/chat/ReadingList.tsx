import type { ReadingPassage } from '@/api/client'
import { cn } from '@/lib/utils'

/** One paper's record (M8.5 Ask each paper): from the stream (`cited`: chunk ids) or from history (`cited`: passages). */
export type ReadingRow = {
  paper_id: string
  label: string
  status: 'found' | 'absent' | 'no_text' | 'model_error'
  answer: string
  low_confidence: boolean
  cited: (string | ReadingPassage)[]
}

const WORDS: Record<ReadingRow['status'], string> = {
  found: 'found',
  absent: "doesn't cover this",
  no_text: 'no text',
  model_error: "couldn't read",
}
const TONES: Record<ReadingRow['status'], string> = {
  found: 'text-foreground',
  absent: 'text-amber-700 dark:text-amber-300',
  no_text: 'text-muted-foreground',
  model_error: 'text-destructive',
}

const statusWord = (row: ReadingRow) =>
  row.status === 'found' && row.low_confidence ? 'found, no passage cited' : WORDS[row.status]

function summary(rows: ReadingRow[]): string {
  const count = (...statuses: ReadingRow['status'][]) => rows.filter((r) => statuses.includes(r.status)).length
  const parts = [`${count('found')} found`, `${count('absent')} don't cover this`]
  const unread = count('no_text', 'model_error')
  if (unread) parts.push(`${unread} couldn't be read`)
  return `Read ${rows.length} papers: ${parts.join(', ')}`
}

function Row({ row, open }: { row: ReadingRow; open: boolean }) {
  const passages = row.cited.filter((c): c is ReadingPassage => typeof c !== 'string')
  return (
    <li className="flex flex-col gap-0.5">
      <span>
        <span className="text-foreground">{row.label}</span>{' '}
        <span className={cn('whitespace-nowrap', TONES[row.status])}>{statusWord(row)}</span>
      </span>
      {open && row.answer && <span className="text-muted-foreground">{row.answer}</span>}
      {open &&
        passages.map((p) => (
          <span key={p.chunk_id} className="text-muted-foreground">
            {`p. ${p.page}${p.section ? `, ${p.section}` : ''}: `}
            <q className="italic">{p.text}</q>
          </span>
        ))}
    </li>
  )
}

/**
 * Ask each paper's records: while reading, a row per paper as it lands; under a saved answer, a summary that opens
 * to each paper's record and its cited passages.
 */
export function ReadingList({ readings, total, live = false }: { readings: ReadingRow[]; total?: number; live?: boolean }) {
  const rows = <ol className="flex flex-col gap-1.5">{readings.map((row) => <Row key={row.paper_id} row={row} open={!live} />)}</ol>
  if (live) {
    return (
      <section aria-label="Papers read" className="flex flex-col gap-1.5 rounded-lg bg-background/60 p-3 text-xs">
        <p aria-live="polite" className="text-muted-foreground">{`Reading ${readings.length} of ${total ?? readings.length} papers`}</p>
        {rows}
      </section>
    )
  }
  return (
    <details className="rounded-lg bg-background/60 p-3 text-xs">
      <summary className="cursor-pointer text-muted-foreground">{summary(readings)}</summary>
      <div className="mt-2">{rows}</div>
    </details>
  )
}
