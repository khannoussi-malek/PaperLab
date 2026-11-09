import { useEffect, useRef, useState } from 'react'
import type { Hit, Paper, ProvenanceOut, ProvNode } from '@/api/client'
import { refreshTree, useImportSearchHits, usePatchSearchHit, useSearchHit, useUploadHitPdf, useWorkspacePapers } from '@/api/queries'
import { useQueryClient } from '@tanstack/react-query'
import { HitPreview } from '@/features/workspace-search/HitPreview'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { readerHref } from '@/lib/route'
import { branchTarget } from '../viewShared'
import { Decisions } from './Decisions'
import { grabLine } from './NextPapers'
import { SummariseNow } from './SummariseNow'
import type { Grab, GrabState } from './useGrab'

type Props = { workspaceId: string; data: ProvenanceOut; node: ProvNode; grab: Grab; grabs: Record<string, GrabState>; focusHeading?: boolean; onReveal: () => void }

const ABSTRACT_CHARS = 600

function Abstract({ text }: { text: string | null | undefined }) {
  const [more, setMore] = useState(false)
  if (!text) return <p className="text-sm text-muted-foreground">No abstract available.</p>
  const long = text.length > ABSTRACT_CHARS
  return (
    <div className="text-sm">
      <p className="whitespace-pre-line">{long && !more ? `${text.slice(0, ABSTRACT_CHARS)}…` : text}</p>
      {long && <button type="button" className="text-xs underline underline-offset-2" onClick={() => setMore(!more)}>{more ? 'show less' : 'show more'}</button>}
    </div>
  )
}

function Fit({ hit, workspaceId, all }: { hit: Hit | undefined; workspaceId: string; all?: boolean }) {
  const fit = hit?.suggestion_relevance ?? null
  return (
    <section className="rounded-md bg-muted/50 p-2 text-sm">
      <h3 className="text-xs font-medium text-muted-foreground">For your question:</h3>
      {fit == null ? (
        <div className="mt-1 flex items-center gap-2"><span>not read yet</span>{hit && <SummariseNow workspaceId={workspaceId} hitId={hit.id} />}</div>
      ) : (
        <>
          <p className="mt-1 font-medium">{`fits ${fit}/5`}</p>
          {hit?.suggestion_note && <p>{hit.suggestion_note}</p>}
          {(hit?.suggestion_quotes ?? []).slice(0, all ? undefined : 2).map((q) => <p key={q} className="mt-1 text-xs italic text-muted-foreground">“{q}”</p>)}
          {hit && <div className="mt-1"><SummariseNow workspaceId={workspaceId} hitId={hit.id} /></div>}
        </>
      )}
    </section>
  )
}

/** The paper the owner is standing on: facts, fit for their question, abstract, PDF, and the decisions. */
export function PaperCard({ workspaceId, data, node, grab, grabs, focusHeading, onReveal }: Props) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (focusHeading) heading.current?.focus() }, []) // eslint-disable-line react-hooks/exhaustive-deps -- once per card; the card is keyed by paper
  const isHit = !node.id.startsWith('paper:')
  const hitQuery = useSearchHit(workspaceId, isHit ? node.id : null)
  const hit = hitQuery.data
  const library: Paper | undefined = useWorkspacePapers(workspaceId).data?.find((p) => p.id === (node.paper_id ?? hit?.paper_id))
  const [details, setDetails] = useState(false)
  const detailsButton = useRef<HTMLButtonElement>(null)
  const target = branchTarget(node)
  const title = hit?.title ?? library?.title ?? node.title
  const byline = [(hit?.authors ?? library?.authors)?.join(', ') || null, hit?.year ?? library?.year ?? node.year, hit?.venue ?? library?.venue].filter(Boolean).join(' · ')
  const paperId = node.paper_id ?? hit?.paper_id ?? null
  const hasPdf = library ? library.has_pdf : hit ? hit.acquisition_status === 'imported' || hit.acquisition_status === 'manual' : false
  // ponytail: HitOut carries no free-copy URL, so only a library paper's oa_url can back this up; add a hit field if one is ever exposed.
  const freeCopy = library?.oa_url ?? null
  const pdfHref = paperId && hasPdf ? readerHref(paperId) : freeCopy
  return (
    <article aria-label="Current paper" className="flex flex-col gap-2 rounded-lg border border-border bg-card p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h2 ref={heading} tabIndex={-1} className="min-w-0 flex-1 font-heading text-base leading-snug outline-none">{title}</h2>
        <div className="flex shrink-0 flex-wrap gap-1.5">
          {pdfHref && <Button asChild size="sm" variant="outline"><a href={pdfHref} {...(pdfHref === freeCopy && { target: '_blank', rel: 'noreferrer' })}>Open PDF</a></Button>}
          {isHit ? <Button ref={detailsButton} type="button" size="sm" variant="outline" onClick={() => setDetails(true)}>Full details</Button>
            : paperId && <Button asChild size="sm" variant="outline"><a href={readerHref(paperId)}>Full details</a></Button>}
        </div>
      </div>
      {byline && <p className="text-xs text-muted-foreground">{byline}</p>}
      <p className="text-xs text-muted-foreground">Level {node.level} · {node.paths === 0 ? 'added by hand' : `reached by ${node.paths} ${node.paths === 1 ? 'route' : 'routes'}`} · {hasPdf ? 'PDF available' : 'no PDF yet'}</p>
      {isHit ? <Fit hit={hit} workspaceId={workspaceId} /> : <p className="text-sm text-muted-foreground">Added by hand: no fit score</p>}
      <Abstract text={hit?.abstract ?? library?.abstract} />
      {grabs[node.id]?.status === 'done' && <p role="status" className="text-xs text-muted-foreground">{grabLine(node, data, grabs[node.id])}</p>}
      <Decisions key={node.id} workspaceId={workspaceId} node={node} hit={hit} target={target} isHit={isHit} grab={grab} pending={grabs[node.id]?.status === 'pending'} onReveal={onReveal} />
      {grabs[node.id]?.status === 'error' && <p role="alert" className="text-xs text-destructive">{(grabs[node.id] as { text: string }).text}</p>}
      {isHit && <DetailsDialog returnFocus={detailsButton} workspaceId={workspaceId} hit={hit} title={node.title} error={hitQuery.error} open={details} onOpenChange={setDetails} />}
    </article>
  )
}

/** Everything about a search hit in one wide, single-frame dialog; the card behind it keeps the branch and snowball controls. */
function DetailsDialog({ returnFocus, workspaceId, hit, title, error, open, onOpenChange }: { returnFocus: React.RefObject<HTMLButtonElement | null>; workspaceId: string; hit: Hit | undefined; title: string; error: Error | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const client = useQueryClient()
  const review = usePatchSearchHit(workspaceId)
  const importHits = useImportSearchHits(workspaceId)
  const upload = useUploadHitPdf(workspaceId)
  // Screening changes the hit and the tree; re-read them.
  const refresh = { onSuccess: () => refreshTree(client, workspaceId) }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onCloseAutoFocus={(e) => { e.preventDefault(); returnFocus.current?.focus() }} className="max-h-[90vh] gap-3 overflow-y-auto p-6 sm:max-w-3xl">
        <DialogHeader><DialogTitle className="pr-8 text-lg leading-snug">{hit ? hit.title || hit.normalized_title : title}</DialogTitle>
          <DialogDescription>Everything PaperLab knows about this paper</DialogDescription></DialogHeader>
        {!hit ? (error ? <p role="alert" className="text-sm text-destructive">{error.message}</p> : <p role="status" className="text-sm text-muted-foreground">Loading the paper…</p>) : <HitPreview
          hit={hit}
          workspaceId={workspaceId}
          wide
          extra={<Fit hit={hit} workspaceId={workspaceId} all />}
          onReview={(hitId, body) => review.mutate({ hitId, body }, refresh)}
          onAddPdf={(hitId) => importHits.mutate([hitId], refresh)}
          addPdfPending={importHits.isPending}
          onUpload={(hitId, file) => upload.mutate({ hitId, file }, refresh)}
          uploadPending={upload.isPending}
        />}
      </DialogContent>
    </Dialog>
  )
}
