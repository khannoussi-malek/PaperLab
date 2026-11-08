import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'
import { refreshTree, useProvenance, useSnowball } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { SidePanel } from './SidePanel'
import { SnowballNext } from './SnowballNext'
import { hiddenIds, NO_FILTERS, TreeFilters } from './TreeFilters'
import { TreeView } from './TreeView'

export function SnowballTreeTab({ workspaceId }: { workspaceId: string }) {
  const { data, isPending, error } = useProvenance(workspaceId)
  const [selected, setSelected] = useState<string | null>(null)
  const [folded, setFolded] = useState<Set<string>>(new Set())
  const [filters, setFilters] = useState(NO_FILTERS)
  const hidden = useMemo(() => (data ? hiddenIds(data, filters) : new Set<string>()), [data, filters])
  const [showStopped, setShowStopped] = useState(false)
  const [opened, setOpened] = useState<Set<string>>(new Set()) // stopped boxes the owner unfolded by hand
  const [busy, setBusy] = useState<string | null>(null)
  const snowball = useSnowball(workspaceId)
  const client = useQueryClient()
  const stopped = useMemo(() => new Set((data?.nodes ?? []).filter((n) => n.branch?.state === 'stopped').map((n) => n.id)), [data])
  // A stopped box is folded by default: it stays, with its mark, but what lies below is hidden.
  const effectiveFolded = useMemo(
    () => (showStopped ? folded : new Set([...folded, ...[...stopped].filter((id) => !opened.has(id))])),
    [folded, stopped, opened, showStopped],
  )
  const toggleFold = useCallback(
    (id: string) => {
      const flip = (prev: Set<string>) => {
        const next = new Set(prev)
        if (!next.delete(id)) next.add(id)
        return next
      }
      if (stopped.has(id) && !showStopped) setOpened(flip)
      else setFolded(flip)
    },
    [stopped, showStopped],
  )
  const find = (target: { hit_id: string } | { paper_id: string }) => {
    const id = 'hit_id' in target ? target.hit_id : (data?.nodes.find((n) => n.paper_id === target.paper_id)?.id ?? null)
    setBusy(id)
    snowball.mutate(
      { seed_hit_ids: 'hit_id' in target ? [target.hit_id] : [], seed_paper_ids: 'paper_id' in target ? [target.paper_id] : [], backward: true, forward: true },
      { onSuccess: () => refreshTree(client, workspaceId), onSettled: () => setBusy(null) },
    )
  }

  if (isPending) return <p className="text-sm text-muted-foreground">Loading the tree…</p>
  if (error || !data) return <p role="alert" className="text-sm text-destructive">Could not load the snowball tree.</p>
  if (data.roots.length === 0) return <p className="text-sm text-muted-foreground">Nothing to draw yet. Run a search first.</p>

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <SnowballNext workspaceId={workspaceId} />
      <div className="flex flex-wrap items-center gap-3">
        <TreeFilters data={data} value={filters} onChange={setFilters} />
        {stopped.size > 0 && (
          <Button type="button" size="sm" variant="outline" onClick={() => setShowStopped((v) => !v)}>
            {showStopped ? 'Hide stopped' : 'Show stopped'}
          </Button>
        )}
      </div>
      {data.truncated && <p className="text-xs text-muted-foreground">Showing the first part of a large tree.</p>}
      <div className="flex min-h-0 flex-1 gap-3">
        <TreeView data={data} selected={selected} onSelect={setSelected} folded={effectiveFolded} onToggleFold={toggleFold} hidden={hidden} snowballing={busy} />
        {selected && <SidePanel workspaceId={workspaceId} data={data} id={selected} busy={busy === selected} onFind={find} />}
      </div>
    </div>
  )
}
