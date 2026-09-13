import { BookOpen, LoaderCircle, TriangleAlert } from 'lucide-react'
import { api, type Paper } from '@/api/client'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { readerHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { FirstPage } from './FirstPage'
import { authorNames, pageCountLabel } from './paperMeta'

const addedDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })

/** The page area while a paper has no readable PDF yet: still ingesting, or failed. */
function PagePlaceholder({ paper }: { paper: Paper }) {
  const failed = paper.status === 'failed'
  return (
    <div className="grid aspect-[612/792] w-full place-items-center rounded-sm bg-muted/60 p-6 text-center text-sm">
      {failed ? (
        <p className="flex flex-col items-center gap-2 text-destructive">
          <TriangleAlert aria-hidden />
          {paper.status_error ?? 'This paper could not be processed.'}
        </p>
      ) : (
        <p className="flex flex-col items-center gap-2 text-muted-foreground">
          <LoaderCircle aria-hidden className="motion-safe:animate-spin" />
          Processing ({paper.status})…
        </p>
      )}
    </div>
  )
}

export function PaperPreview({ paper }: { paper: Paper }) {
  const authors = authorNames(paper.authors)
  const facts = [paper.year, paper.venue, pageCountLabel(paper.page_count)].filter(Boolean)
  const fileUrl = api.paperFileUrl(paper.id)

  return (
    <aside
      aria-label="Paper preview"
      className={cn('paper-preview flex flex-col gap-4 rounded-xl p-4 ring-1 ring-glass-border', glass)}
    >
      {paper.status === 'ready' ? (
        <FirstPage key={fileUrl} url={fileUrl} title={paper.title} />
      ) : (
        <PagePlaceholder paper={paper} />
      )}

      <div className="flex flex-col gap-1">
        <h2 className="font-heading text-xl leading-snug font-semibold wrap-anywhere">{paper.title}</h2>
        {authors.length > 0 && <p className="text-sm">{authors.join(', ')}</p>}
        {facts.length > 0 && <p className="text-sm text-muted-foreground">{facts.join(' · ')}</p>}
        <p className="text-xs text-muted-foreground">Added {addedDate(paper.created_at)}</p>
        {paper.doi && (
          <a
            href={`https://doi.org/${encodeURIComponent(paper.doi)}`}
            target="_blank"
            rel="noreferrer"
            className="w-fit text-xs text-primary hover:underline"
          >
            doi:{paper.doi}
          </a>
        )}
      </div>

      {paper.abstract && <p className="line-clamp-6 text-sm text-muted-foreground">{paper.abstract}</p>}

      <Button asChild variant="outline" className="self-start">
        <a href={readerHref(paper.id)}>
          <BookOpen aria-hidden />
          Open in reader
        </a>
      </Button>
    </aside>
  )
}
