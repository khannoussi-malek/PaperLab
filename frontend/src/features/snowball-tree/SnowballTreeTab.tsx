import { useCallback, useMemo, useState } from 'react'
import { usePaths, useProvenance } from '@/api/queries'
import type { ProvenanceOut } from '@/api/client'
import { decisionWord } from './levelText'
import { hiddenIds, NO_FILTERS, TreeFilters } from './TreeFilters'
import { TreeView } from './TreeView'

function SidePanel({ workspaceId, data, id }: { workspaceId: string; data: ProvenanceOut; id: string }) {
  const node = data.nodes.find((n) => n.id === id)
  const root = data.roots.find((r) => r.id === id)
  const extra = node && node.paths > 1 ? id : null
  const paths = usePaths(workspaceId, extra).data
  const name = (key: string) => data.nodes.find((n) => n.id === key)?.title ?? data.roots.find((r) => r.id === key)?.label ?? key
  return (
    <aside className="w-72 shrink-0 overflow-auto rounded-lg border border-border bg-card p-3 text-sm">
      <h3 className="font-heading text-base">{node?.title ?? root?.label}</h3>
      {node && (
        <p className="mt-1 text-xs text-muted-foreground">
          {node.year ? `${node.year} · ` : ''}Level {node.level} · {decisionWord(node.decision)}
        </p>
      )}
      {paths && paths.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-xs">
          {paths.map((p) => (
            <li key={p.map((l) => l.parent).join('>')}>
              {[...p.map((l) => name(l.parent)), name(p[p.length - 1].child)].join(' → ')}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

export function SnowballTreeTab({ workspaceId }: { workspaceId: string }) {
  const { data, isPending, error } = useProvenance(workspaceId)
  const [selected, setSelected] = useState<string | null>(null)
  const [folded, setFolded] = useState<Set<string>>(new Set())
  const [filters, setFilters] = useState(NO_FILTERS)
  const hidden = useMemo(() => (data ? hiddenIds(data, filters) : new Set<string>()), [data, filters])
  const toggleFold = useCallback(
    (id: string) =>
      setFolded((prev) => {
        const next = new Set(prev)
        if (!next.delete(id)) next.add(id)
        return next
      }),
    [],
  )

  if (isPending) return <p className="text-sm text-muted-foreground">Loading the tree…</p>
  if (error || !data) return <p role="alert" className="text-sm text-destructive">Could not load the snowball tree.</p>
  if (data.roots.length === 0) return <p className="text-sm text-muted-foreground">Nothing to draw yet. Run a search first.</p>

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <TreeFilters data={data} value={filters} onChange={setFilters} />
      {data.truncated && <p className="text-xs text-muted-foreground">Showing the first part of a large tree.</p>}
      <div className="flex min-h-0 flex-1 gap-3">
        <TreeView data={data} selected={selected} onSelect={setSelected} folded={folded} onToggleFold={toggleFold} hidden={hidden} />
        {selected && <SidePanel workspaceId={workspaceId} data={data} id={selected} />}
      </div>
    </div>
  )
}
