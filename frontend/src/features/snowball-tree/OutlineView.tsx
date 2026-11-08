import { useEffect, useMemo, useRef, useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { useSetBranch } from '@/api/queries'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { isUnknown, PARENT_NOT_RECORDED, tidyLayout, type Box } from './layout'
import { decisionWord } from './levelText'
import { Legend } from './TreeView'
import { branchTarget, decisionKey } from './viewShared'

type Props = { workspaceId: string; data: ProvenanceOut; selected: string | null; onSelect: (id: string | null) => void; hidden: Set<string> }
type Row = { box: Box; depth: number; kind: string; parent: string | null; kids: number }

const HINT = 'Keys: ↑↓ move · → open · ← close · Enter details · g go further · s stop · u undecided'
const DIRECTION_LABEL: Record<string, string> = { cites: 'Its references', cited_by: 'Papers citing it' }
const KIND_WORD: Record<string, string> = { cites: 'cites', cited_by: 'cited by' }
const EDGE: Record<string, string> = { relevant: 'border-included', not_relevant: 'border-destructive', none: 'border-border' }
const BOTH = ['cites', 'cited_by']

function branchTag(box: Box): string {
  const b = box.node?.branch
  if (!b) return ''
  if (b.state === 'go_further') return ` · go further: ${b.directions.map((d) => DIRECTION_LABEL[d] ?? d).join(', ')}`
  return ` · stopped${b.reason ? `: ${b.reason}` : ''}`
}

function rowText(r: Row): string {
  const { box } = r
  if (!box.node) return `search ${box.root!.label}`
  const title = isUnknown(box.id) ? PARENT_NOT_RECORDED : box.node.title
  return `${r.kind} ${title} · L${box.node.level} · ${decisionWord(box.node.decision)}${branchTag(box)}`
}

/** Work through the papers one by one: grouped by search, nested by parent, driven from the keyboard. */
export function OutlineView({ workspaceId, data, selected, onSelect, hidden }: Props) {
  const layout = useMemo(() => tidyLayout(data.nodes, data.links, data.roots, new Set(), hidden), [data, hidden])
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const setBranch = useSetBranch(workspaceId)
  const [focus, setFocus] = useState<string | null>(null)
  const refs = useRef(new Map<string, HTMLElement>())
  const moved = useRef(false)

  const { rows, kidsOf } = useMemo(() => {
    const kidsOf = new Map<string, Row[]>()
    const byId = new Map(layout.boxes.map((b) => [b.id, b]))
    const parentOf = new Map(layout.edges.map((e) => [e.to, e]))
    const all = new Map<string, Row>()
    const depthOf = (id: string): number => (parentOf.has(id) ? depthOf(parentOf.get(id)!.from) + 1 : 0)
    for (const box of layout.boxes) {
      const e = parentOf.get(box.id)
      all.set(box.id, { box, depth: depthOf(box.id), kind: e ? (KIND_WORD[e.kind] ?? e.kind) : 'cites', parent: e?.from ?? null, kids: 0 })
    }
    for (const r of all.values()) if (r.parent && byId.has(r.parent)) kidsOf.set(r.parent, [...(kidsOf.get(r.parent) ?? []), r])
    for (const [id, k] of kidsOf) all.get(id)!.kids = k.length
    // layout.boxes runs parent before child, so skipping a closed parent's subtree is one pass
    const hiddenBy = new Set<string>()
    const visible = [...all.values()].filter((r) => {
      if (r.parent && (closed.has(r.parent) || hiddenBy.has(r.parent))) { hiddenBy.add(r.box.id); return false }
      return true
    })
    return { rows: visible, kidsOf }
  }, [layout, closed])

  const current = focus && rows.some((r) => r.box.id === focus) ? focus : (rows[0]?.box.id ?? null)
  useEffect(() => {
    if (moved.current && current) refs.current.get(current)?.focus()
    moved.current = false // only a key press moves focus; a refetch or filter change must not steal it
  }, [current, rows])

  const go = (id: string) => { if (id !== current) { moved.current = true; setFocus(id) } }
  const toggle = (id: string, open: boolean) => setClosed((c) => { const n = new Set(c); if (open) n.delete(id); else n.add(id); return n })
  const setState = (box: Box, state: 'go_further' | 'stopped' | null) => {
    const target = box.node && branchTarget(box.node)
    if (!target) return
    const now = box.node!.branch
    // Already so: skip, which also keeps a stop reason the owner wrote.
    if ((now?.state ?? null) === state && (state !== 'go_further' || BOTH.every((d) => now!.directions.includes(d)))) return
    setBranch.mutate({ ...target, state, directions: state === 'go_further' ? BOTH : [], reason: null })
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const i = rows.findIndex((r) => r.box.id === current)
    const row = rows[i]
    if (!row || e.ctrlKey || e.metaKey || e.altKey) return
    const open = row.kids > 0 && !closed.has(row.box.id)
    const actions: Record<string, () => void> = {
      ArrowDown: () => rows[i + 1] && go(rows[i + 1].box.id),
      ArrowUp: () => rows[i - 1] && go(rows[i - 1].box.id),
      ArrowRight: () => (row.kids === 0 ? undefined : open ? go(kidsOf.get(row.box.id)![0].box.id) : toggle(row.box.id, true)),
      ArrowLeft: () => (open ? toggle(row.box.id, false) : row.parent && go(row.parent)),
      Enter: () => onSelect(row.box.id),
      g: () => setState(row.box, 'go_further'),
      s: () => setState(row.box, 'stopped'),
      u: () => setState(row.box, null),
    }
    const act = actions[e.key]
    if (!act) return
    e.preventDefault()
    act()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <Legend />
      <p className="text-xs text-muted-foreground">{HINT}</p>
      {setBranch.isError && <p role="alert" className="text-xs text-destructive">{setBranch.error.message}</p>}
      <ul role="tree" aria-label="Snowball outline" onKeyDown={onKeyDown} className="min-h-0 flex-1 overflow-auto rounded-lg border border-border bg-card p-2 text-sm">
        {rows.map((r) => (
          <li
            key={r.box.id} role="treeitem" aria-level={r.depth + 1} aria-selected={selected === r.box.id}
            aria-expanded={r.kids > 0 ? !closed.has(r.box.id) : undefined}
            tabIndex={r.box.id === current ? 0 : -1} data-faded={r.box.faded} data-decision={r.box.node ? decisionKey(r.box.node) : 'root'}
            ref={(el) => { if (el) refs.current.set(r.box.id, el); else refs.current.delete(r.box.id) }}
            style={{ paddingLeft: r.depth * 16 + 8 }}
            onClick={() => { go(r.box.id); onSelect(r.box.id) }}
            onFocus={() => setFocus(r.box.id)}
            className={cn('list-none cursor-pointer rounded border-l-4 px-2 py-1', EDGE[r.box.node ? decisionKey(r.box.node) : 'none'], 'outline-none focus-visible:ring-2 focus-visible:ring-ring', r.box.faded && 'opacity-40', selected === r.box.id && 'bg-accent')}
          >
            {r.kids > 0 && (
              <button
                type="button" aria-hidden tabIndex={-1} title={closed.has(r.box.id) ? 'Unfold' : 'Fold'}
                className="mr-1 inline-flex align-middle"
                onClick={(e) => { e.stopPropagation(); toggle(r.box.id, closed.has(r.box.id)) }}
              >
                {closed.has(r.box.id) ? <ChevronRight className="size-3" /> : <ChevronDown className="size-3" />}
              </button>
            )}
            {rowText(r)}
          </li>
        ))}
      </ul>
    </div>
  )
}
