import type { Paper } from '@/api/client'
import { useTriageEvents } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { GetPdfActions } from '@/features/library/GetPdfActions'
import { byline, pageCountLabel } from '@/features/library/paperMeta'
import { readingChip } from '@/features/reading/passes'
import { describeEvent } from '@/features/reading/historyText'
import { RetractionBanner } from '@/features/reader/RetractionBanner'
import { SourceBadges } from '@/features/reader/SourceBadges'
import { useConclusion } from './useConclusion'

function Conclusion({ paper, onShowInPdf }: { paper: Paper; onShowInPdf?: (page: number) => void }) {
  const c = useConclusion(paper.id, paper.has_pdf)
  if (c.status === 'loading') return <div data-testid="conclusion-loading" aria-hidden className="h-12 rounded-md bg-muted/40" />
  if (c.status === 'error') return <p className="text-sm text-muted-foreground">Couldn't load the conclusion. The abstract above is still here.</p>
  if (c.status === 'none') {
    return c.noSections ? <p className="text-sm text-muted-foreground">Full text isn't ready yet</p> : null
  }
  return (
    <section aria-label={c.title} className="space-y-1">
      <h3 className="text-sm font-medium">{c.title} · p. {c.page}</h3>
      <p className="text-sm leading-relaxed text-muted-foreground">{c.text}</p>
      {onShowInPdf && c.page !== null && (
        <Button variant="outline" size="sm" onClick={() => onShowInPdf(c.page!)}>Show in PDF (p. {c.page})</Button>
      )}
    </section>
  )
}

function DecidedLine({ paper }: { paper: Paper }) {
  const chip = readingChip(paper.reading_pass ?? 0, paper.triage)
  const { data } = useTriageEvents(paper.id, true)
  const last = [...(data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  return (
    <p className="text-sm text-muted-foreground">
      <span data-testid="triage-chip" className="font-medium text-foreground">{chip}</span>
      {last && ` · ${describeEvent(last).when}`}
    </p>
  )
}

/** One paper to decide on: the abstract in full and the conclusion, never the title alone. */
export function TriageCard({ paper, onShowInPdf }: { paper: Paper; onShowInPdf?: (page: number) => void }) {
  const decided = Boolean(paper.triage) || (paper.reading_pass ?? 0) > 0
  const meta = [byline(paper), pageCountLabel(paper.page_count)].filter(Boolean).join(' · ')
  return (
    <article
      role="group"
      aria-labelledby={`triage-title-${paper.id}`}
      data-triage-card
      className="paper-surface flex flex-col gap-3 rounded-xl border border-[#e6dfcc] p-6 shadow-[0_22px_40px_-16px_rgba(15,23,42,.45)]"
    >
      {paper.is_retracted && <RetractionBanner paper={paper} />}
      <h2 id={`triage-title-${paper.id}`} className="font-heading text-xl font-semibold wrap-anywhere">{paper.title}</h2>
      {meta && <p className="text-sm text-muted-foreground">{meta}</p>}
      <div className="flex flex-wrap gap-1.5"><SourceBadges paper={paper} /></div>
      {decided && <DecidedLine paper={paper} />}
      <div
        aria-label="Abstract"
        tabIndex={0}
        className="max-h-64 overflow-y-auto whitespace-pre-line rounded-md text-sm leading-relaxed outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {paper.abstract?.trim() || <span className="text-muted-foreground">No abstract</span>}
      </div>
      {!paper.has_pdf && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">No PDF for this paper.</p>
          <GetPdfActions paperId={paper.id} title={paper.title} />
        </div>
      )}
      <Conclusion paper={paper} onShowInPdf={onShowInPdf} />
    </article>
  )
}
