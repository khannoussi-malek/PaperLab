import type { Paper } from '@/api/client'
import { usePaperEvents } from '@/api/queries'
import { provenanceLines } from './detailsSource'

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })

const CHECK_RESULT = { none: 'none found', found: 'found', error: 'the check failed' } as const
/** How a PDF came in, from the backend's own words (retrieved_hits.ARRIVALS). */
const HOW: Record<string, string> = { manual: 'uploaded', imported: 'found' }

/** The Details dialog's read-only part: where each group of details came from, the last free-copy check, the history. */
export function PaperProvenance({ paper }: { paper: Paper }) {
  const events = usePaperEvents(paper.id)
  const lines = provenanceLines(paper)
  const checked = !paper.has_pdf && paper.pdf_checked_at && paper.pdf_check_result
  // pdf_found feeds the library's Found PDFs notice; the arrival itself is its pdf_attached, so a find shows once
  const arrivals = (events.data ?? []).filter((e) => e.kind === 'pdf_attached')
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
      {arrivals.length > 0 && (
        <section aria-labelledby="history-heading">
          <h3 id="history-heading" className="font-medium text-foreground">History</h3>
          <ul>
            {arrivals.map((e) => (
              <li key={e.id}>
                PDF added {day(e.created_at)}
                {HOW[String(e.detail.how)] ? ` (${HOW[String(e.detail.how)]})` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
