import type { Paper } from '@/api/client'
import { usePaperEvents } from '@/api/queries'
import { provenanceLines } from './detailsSource'

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })

const CHECK_RESULT = { none: 'none found', found: 'found', error: 'the check failed' } as const

/** The Details dialog's read-only part: where each group of details came from, the last free-copy check, the history. */
export function PaperProvenance({ paper }: { paper: Paper }) {
  const events = usePaperEvents(paper.id)
  const lines = provenanceLines(paper)
  const checked = !paper.has_pdf && paper.pdf_checked_at && paper.pdf_check_result
  return (
    <div className="grid gap-3 text-sm text-muted-foreground">
      {lines.length > 0 && (
        <section aria-labelledby="provenance-heading">
          <h3 id="provenance-heading" className="font-medium text-foreground">Where these details came from</h3>
          <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul>
        </section>
      )}
      {checked && (
        <p>
          Last checked for a free copy: {day(paper.pdf_checked_at!)}, {CHECK_RESULT[paper.pdf_check_result!]}
        </p>
      )}
      {events.data && events.data.length > 0 && (
        <section aria-labelledby="history-heading">
          <h3 id="history-heading" className="font-medium text-foreground">History</h3>
          <ul>
            {events.data.map((e) => (
              <li key={e.id}>
                {e.kind === 'pdf_found' ? 'Free PDF found' : 'PDF added'} {day(e.created_at)}
                {e.kind === 'pdf_attached' && e.detail.how ? ` (${e.detail.how})` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
