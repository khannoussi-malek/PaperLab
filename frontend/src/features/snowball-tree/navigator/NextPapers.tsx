import { useId } from 'react'
import type { ProvenanceOut, ProvNode } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { branchTarget } from '../viewShared'
import { decisionWord } from '../levelText'
import { SummariseNow } from './SummariseNow'
import type { Grab, GrabState } from './useGrab'

export const childrenOf = (data: ProvenanceOut, parentId: string, kind?: string) =>
  [...new Set(data.links.filter((l) => l.parent === parentId && (kind === undefined || l.kind === kind)).map((l) => l.child))]

type Props = {
  data: ProvenanceOut
  workspaceId: string
  parentId: string
  onStep: (parentId: string, childId: string, kind: string) => void
  grab: Grab
  grabs: Record<string, GrabState>
  dimmed?: boolean
}

export function grabLine(node: ProvNode, data: ProvenanceOut, state: GrabState | undefined) {
  const id = node.id
  if (state?.status === 'pending') return 'Grabbing…'
  if (state?.status === 'done' || node.snowballed.length > 0) return `✓ grabbed · ${childrenOf(data, id, 'cites').length} cites · ${childrenOf(data, id, 'cited_by').length} citing`
  return '⤓ Grab next papers'
}

function Row({ node, kind, workspaceId, data, onStep, grab, grabs, parentId }: { node: ProvNode; kind: string } & Props) {
  const target = branchTarget(node)
  const isHit = target !== null && 'hit_id' in target
  const fit = node.relevance ?? null // from the tree, so a row costs no request; the card reads the full hit
  const state = grabs[node.id]
  const titleId = useId() // the buttons keep their visible text as their name and point at the title for context
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-border bg-card p-2 text-sm">
      <div className="flex items-baseline gap-2">
        <span id={titleId} className="min-w-0 flex-1 truncate font-medium" title={node.title}>{node.title}</span>
        {node.year ? <span className="shrink-0 text-xs text-muted-foreground">{node.year}</span> : null}
      </div>
      {node.reason && <p className="line-clamp-1 text-xs text-muted-foreground">{node.reason}</p>}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {!isHit ? <span>no fit score</span> : fit != null ? <span className="rounded-full bg-muted px-2 py-0.5">{`fits ${fit}/5`}</span> : (
          <>
            <span className="rounded-full bg-muted px-2 py-0.5">not read yet</span>
            <SummariseNow workspaceId={workspaceId} hitId={node.id} describedBy={titleId} />
          </>
        )}
        <span className="text-muted-foreground">{decisionWord(node.decision)}</span>
        <span className="flex-1" />
        {target && (
          <Button type="button" size="xs" variant="ghost" aria-describedby={titleId} disabled={state?.status === 'pending'} onClick={() => grab(node.id, target)}>
            {grabLine(node, data, state)}
          </Button>
        )}
        <Button type="button" size="xs" aria-describedby={titleId} onClick={() => onStep(parentId, node.id, kind)}>Step in ›</Button>
      </div>
      {state?.status === 'error' && <p role="alert" className="text-xs text-destructive">{state.text}</p>}
    </li>
  )
}

/** The papers one step on from `parentId`: a search lists its first papers; a paper lists what it cites and what cites it. */
export function NextPapers(props: Props) {
  const { data, parentId, dimmed } = props
  const byId = new Map(data.nodes.map((n) => [n.id, n]))
  const list = (kind?: string) => (
    <ul className="flex flex-col gap-2">
      {data.links
        .filter((l) => l.parent === parentId && (kind === undefined || l.kind === kind))
        .filter((l, i, all) => all.findIndex((x) => x.child === l.child) === i && byId.has(l.child))
        .map((l) => <Row key={l.child} node={byId.get(l.child)!} kind={l.kind} {...props} />)}
    </ul>
  )
  const wrap = `min-w-0 ${dimmed ? 'opacity-50' : ''}`
  if (parentId.startsWith('root:')) return <div data-testid="next-papers" className={wrap}>{list()}</div>
  const snowballed = byId.get(parentId)?.snowballed ?? []
  const tab = (kind: 'cites' | 'cited_by', label: string) => {
    const count = snowballed.includes(kind) ? String(childrenOf(data, parentId, kind).length) : 'not fetched'
    return { kind, text: `${label} (${count})`, fetched: snowballed.includes(kind) }
  }
  const tabs = [tab('cites', 'Papers it cites'), tab('cited_by', 'Papers citing it')]
  const node = byId.get(parentId)
  const target = node ? branchTarget(node) : null
  return (
    <div data-testid="next-papers" className={wrap}>
      <Tabs key={parentId} defaultValue="cites">
        <TabsList>{tabs.map((t) => <TabsTrigger key={t.kind} value={t.kind}>{t.text}</TabsTrigger>)}</TabsList>
        {tabs.map((t) => (
          <TabsContent key={t.kind} value={t.kind}>
            {!t.fetched ? (
              <div className="flex flex-col items-start gap-2 py-2 text-sm text-muted-foreground">
                <p>Not fetched yet.</p>
                {target && (
                  <Button type="button" size="sm" disabled={props.grabs[parentId]?.status === 'pending'}
                    onClick={() => props.grab(parentId, target, { backward: t.kind === 'cites', forward: t.kind === 'cited_by' })}>
                    {t.kind === 'cites' ? 'Find its references' : 'Find papers citing it'}
                  </Button>
                )}
              </div>
            ) : childrenOf(data, parentId, t.kind).length === 0 ? <p className="py-2 text-sm text-muted-foreground">None found.</p> : list(t.kind)}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
