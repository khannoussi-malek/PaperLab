import type { UseQueryResult } from '@tanstack/react-query'
import { ExternalLink, LoaderCircle, Plus } from 'lucide-react'
import { useMemo, useRef, type CSSProperties } from 'react'
import { api, type Reference, type References } from '@/api/client'
import { useImportReference } from '@/api/queries'
import { delayedIn, popIn } from '@/components/motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { citationsLabel, pageLink } from '@/features/discovery/candidateMeta'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { FirstPage } from '@/features/library/FirstPage'
import { byline } from '@/features/library/paperMeta'
import { cocitationBadge } from '@/features/references/referencesMeta'
import { readerHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { cardView, UNMATCHED_LINES, type CardView } from './citationMatch'
import { citationCardId, type Citation } from './citations'

/** The note hover card's size, motion and surface (D147): strong glass, since the page's text sits right behind it. */
const SURFACE =
  'citation-card pointer-events-auto absolute z-10 flex w-80 origin-top-left flex-col gap-2 rounded-xl border border-glass-border bg-glass-strong p-3 text-sm shadow-lg backdrop-blur-lg backdrop-saturate-150'

type Matched = Extract<CardView, { reference: Reference }>
type Unmatched = Extract<CardView, { kind: 'unmatched' }>

function OpenPage({ href }: { href: string }) {
  return (
    <Button size="sm" variant="ghost" asChild>
      <a href={href} target="_blank" rel="noreferrer">
        <ExternalLink aria-hidden />
        Open page
      </a>
    </Button>
  )
}

/** Title, byline · citations, and the badges: what the References row shows, from the same helpers. */
function Details({ view }: { view: Matched }) {
  const { reference } = view
  const meta = [byline(reference), citationsLabel(reference.cited_by_count)].filter(Boolean).join(' · ')
  const shared = cocitationBadge(reference.cocitation, 'cites')
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <p title={reference.title} className="line-clamp-3 font-heading font-semibold wrap-anywhere">
        {reference.title}
      </p>
      {meta && <p className="text-muted-foreground">{meta}</p>}
      <div className="flex flex-wrap gap-1">
        {view.kind === 'free-pdf' && <Badge variant="secondary">PDF</Badge>}
        {view.kind === 'details' && <Badge variant="outline">No free PDF</Badge>}
        {shared && (
          <Badge variant="outline" className="font-normal text-muted-foreground">
            {shared}
          </Badge>
        )}
      </div>
    </div>
  )
}

/** In library, Free PDF and Details only (D146): the cited paper, and what the reader can do with it. */
function MatchedBody({ view, paperId }: { view: Matched; paperId: string }) {
  const importRef = useImportReference(paperId)
  const { reference } = view
  const link = pageLink({ ...reference, core_id: null })
  const fileUrl = reference.paper_id ? api.paperFileUrl(reference.paper_id) : null

  // A keyboard user's focus was on Add to library; once that add turns this card into In library, that button
  // unmounts and focus would otherwise fall to <body>. No state, no effect: a ref carries the "just added" flag, and
  // the Open in PaperLab link's own callback ref follows focus there the moment it mounts — which, for a reference
  // that had no `paper_id` before, only ever happens right after this add, never on a plain hover.
  const focusAfterAdd = useRef(false)
  const focusOpenInPaperLab = (el: HTMLAnchorElement | null) => {
    if (!el || !focusAfterAdd.current) return
    focusAfterAdd.current = false
    el.focus()
  }

  return (
    <>
      {fileUrl ? (
        <div className="grid grid-cols-[6rem_1fr] gap-3">
          <FirstPage key={fileUrl} url={fileUrl} title={reference.title} />
          <Details view={view} />
        </div>
      ) : (
        <Details view={view} />
      )}
      <div className="flex flex-wrap items-center gap-2">
        {reference.paper_id && (
          <Button size="sm" asChild>
            <a ref={focusOpenInPaperLab} href={readerHref(reference.paper_id)}>
              Open in PaperLab
            </a>
          </Button>
        )}
        {view.kind === 'free-pdf' && (
          <Button
            size="sm"
            aria-disabled={importRef.isPending || undefined}
            className="aria-disabled:opacity-50"
            onClick={() => {
              if (importRef.isPending) return
              focusAfterAdd.current = true
              importRef.mutate(
                { refId: reference.id },
                { onError: () => { focusAfterAdd.current = false } },
              )
            }}
          >
            {importRef.isPending ? <LoaderCircle aria-hidden className="motion-safe:animate-spin" /> : <Plus aria-hidden />}
            {importRef.isPending ? 'Adding…' : 'Add to library'}
          </Button>
        )}
        {link && <OpenPage href={link} />}
      </div>
      {importRef.error && <ErrorAlert message={importRef.error.message} />}
    </>
  )
}

/** The entry as the PDF prints it, and what the reader knows about the paper's references. */
function UnmatchedBody({ view, onOpenReferences }: { view: Unmatched; onOpenReferences: () => void }) {
  const line = UNMATCHED_LINES[view.state]
  return (
    <>
      <p className="text-xs text-muted-foreground">From this paper's reference list</p>
      <p className="max-h-40 overflow-auto wrap-anywhere">{view.text}</p>
      {line && (
        <p role={view.state === 'fetching' ? 'status' : undefined} className="text-muted-foreground">
          {line}
        </p>
      )}
      {(view.openReferences || view.doi) && (
        <div className="flex flex-wrap items-center gap-2">
          {view.openReferences && (
            <Button size="sm" variant="ghost" onClick={onOpenReferences}>
              Open References
            </Button>
          )}
          {view.doi && <OpenPage href={`https://doi.org/${view.doi}`} />}
        </div>
      )}
    </>
  )
}

type Props = {
  citation: Citation
  paperId: string
  /** The paper's `cites` listing, shared with the References tab. */
  references: Pick<UseQueryResult<References>, 'data' | 'isError'>
  /** Position inside the page overlay, in CSS pixels of the page. */
  style: CSSProperties
  onPointerEnter: () => void
  onPointerLeave: () => void
  onOpenReferences: () => void
}

/** D146: which paper `[N]` is, and whether it is in the library. No card ever shows both details and the raw entry. */
export function CitationCard({ citation, paperId, references, style, onPointerEnter, onPointerLeave, onOpenReferences }: Props) {
  const { data, isError } = references
  // Matching runs only for the open card, and again only when the listing changes (D149).
  const view = useMemo(() => cardView(citation, { data, isError }), [citation, data, isError])
  return (
    <section
      id={citationCardId(citation)}
      aria-label={`Reference ${citation.label}`}
      className={cn(SURFACE, popIn)}
      style={style}
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
    >
      <p className="text-xs text-muted-foreground tabular-nums">Reference {citation.label}</p>
      {view.kind === 'loading' && <p className={cn('text-muted-foreground', delayedIn)}>Loading…</p>}
      {view.kind === 'unreadable' && (
        <p className="text-muted-foreground">
          This entry couldn't be read from the PDF. Click the citation to see it in the list.
        </p>
      )}
      {view.kind === 'unmatched' && <UnmatchedBody view={view} onOpenReferences={onOpenReferences} />}
      {'reference' in view && <MatchedBody view={view} paperId={paperId} />}
    </section>
  )
}
