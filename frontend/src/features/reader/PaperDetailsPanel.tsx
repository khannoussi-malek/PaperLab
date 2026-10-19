import type { Paper } from '@/api/client'
import { GetPdfActions } from '@/features/library/GetPdfActions'
import { Term } from '@/features/workspaces/Term'
import { detailsSourceLine } from './detailsSource'
import { NoPdfBadge } from './SourceBadges'

/** What the pages area shows for a paper saved without its PDF: what PaperLab knows about it, the abstract given most room. */
export function PaperDetailsPanel({ paper }: { paper: Paper }) {
  const source = detailsSourceLine(paper)
  const facts = [paper.year, paper.venue].filter(Boolean).join(' · ')
  return (
    <section aria-label="Paper details">
      <article className="mx-auto flex max-w-2xl flex-col gap-6 px-2 py-10">
        <header className="flex flex-col gap-3">
          <h2 className="font-heading text-2xl leading-snug font-semibold wrap-anywhere">{paper.title}</h2>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <NoPdfBadge />
            {source && <Term term="detailsSource">{source}</Term>}
          </div>
          <GetPdfActions paperId={paper.id} title={paper.title} />
        </header>
        {(paper.authors.length > 0 || facts || paper.doi) && (
          <div className="flex flex-col gap-1 text-sm">
            {paper.authors.length > 0 && <p>{paper.authors.join(', ')}</p>}
            {facts && <p className="text-muted-foreground">{facts}</p>}
            {paper.doi && (
              <a
                href={`https://doi.org/${encodeURIComponent(paper.doi)}`}
                target="_blank"
                rel="noreferrer"
                className="w-fit text-primary hover:underline"
              >
                doi:{paper.doi}
              </a>
            )}
          </div>
        )}
        {paper.abstract ? (
          <section aria-label="Abstract" className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Abstract</h3>
            <p className="paper-abstract leading-relaxed whitespace-pre-line">{paper.abstract}</p>
          </section>
        ) : (
          <p className="text-sm text-muted-foreground">PaperLab has no abstract for this paper.</p>
        )}
      </article>
    </section>
  )
}
