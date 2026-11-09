import { useState } from 'react'
import type { Hit, Paper, ProvenanceOut, ProvNode } from '@/api/client'
import { useSearchHit, useWorkspacePapers } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { readerHref } from '@/lib/route'
import { SidePanel } from '../SidePanel'
import { branchTarget } from '../viewShared'
import { Decisions } from './Decisions'
import { SummariseNow } from './SummariseNow'
import type { Grab, GrabState } from './useGrab'

type Props = { workspaceId: string; data: ProvenanceOut; node: ProvNode; grab: Grab; grabs: Record<string, GrabState> }

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

function Fit({ hit, workspaceId }: { hit: Hit | undefined; workspaceId: string }) {
  const fit = hit?.suggestion_relevance ?? null
  return (
    <section className="rounded-md bg-muted/50 p-2 text-sm">
      <h3 className="text-xs font-medium text-muted-foreground">For your question:</h3>
      {fit == null ? (
        <div className="mt-1 flex items-center gap-2"><span>not read yet</span>{hit && <SummariseNow workspaceId={workspaceId} hitId={hit.id} />}</div>
      ) : (
        <>
          <p className="mt-1 font-medium">{`fits ${fit}/5`}</p>
          {hit?.suggestion_reason && <p>{hit.suggestion_reason}</p>}
          {(hit?.suggestion_quotes ?? []).slice(0, 2).map((q) => <p key={q} className="mt-1 text-xs italic text-muted-foreground">“{q}”</p>)}
          {hit && <div className="mt-1"><SummariseNow workspaceId={workspaceId} hitId={hit.id} /></div>}
        </>
      )}
    </section>
  )
}

/** The paper the owner is standing on: facts, fit for their question, abstract, PDF, and the decisions. */
export function PaperCard({ workspaceId, data, node, grab, grabs }: Props) {
  const isHit = !node.id.startsWith('paper:')
  const hit = useSearchHit(workspaceId, isHit ? node.id : null).data
  const library: Paper | undefined = useWorkspacePapers(workspaceId).data?.find((p) => p.id === (node.paper_id ?? hit?.paper_id))
  const [details, setDetails] = useState(false)
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
      <h2 className="font-heading text-base leading-snug">{title}</h2>
      {byline && <p className="text-xs text-muted-foreground">{byline}</p>}
      <p className="text-xs text-muted-foreground">Level {node.level} · reached by {node.paths} {node.paths === 1 ? 'route' : 'routes'} · {hasPdf ? 'PDF available' : 'no PDF yet'}</p>
      {isHit ? <Fit hit={hit} workspaceId={workspaceId} /> : <p className="text-sm text-muted-foreground">Added by hand: no fit score</p>}
      <Abstract text={hit?.abstract ?? library?.abstract} />
      <div className="flex flex-wrap gap-1.5">
        {pdfHref && <Button asChild size="sm" variant="outline"><a href={pdfHref} {...(pdfHref === freeCopy && { target: '_blank', rel: 'noreferrer' })}>Open PDF</a></Button>}
        {isHit ? <Button type="button" size="sm" variant="outline" onClick={() => setDetails(true)}>Full details</Button>
          : paperId && <Button asChild size="sm" variant="outline"><a href={readerHref(paperId)}>Full details</a></Button>}
        {target && node.snowballed.length === 0 && (
          <Button type="button" size="sm" disabled={grabs[node.id]?.status === 'pending'} onClick={() => grab(node.id, target)}>Find citing &amp; cited papers</Button>
        )}
      </div>
      <Decisions key={node.id} workspaceId={workspaceId} node={node} target={target} isHit={isHit} grab={grab} />
      {grabs[node.id]?.status === 'error' && <p role="alert" className="text-xs text-destructive">{(grabs[node.id] as { text: string }).text}</p>}
      {isHit && (
        <Dialog open={details} onOpenChange={setDetails}>
          <DialogContent className="max-h-[85vh] overflow-auto sm:max-w-xl">
            <DialogTitle className="sr-only">Full details</DialogTitle>
            <SidePanel workspaceId={workspaceId} data={data} id={node.id} busy={false} onFind={(t) => target && grab(node.id, t)} />
          </DialogContent>
        </Dialog>
      )}
    </article>
  )
}
