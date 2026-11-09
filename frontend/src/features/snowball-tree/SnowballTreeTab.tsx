import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useRef, useState } from 'react'
import { refreshTree, useProvenance, useSearchRuns, useSnowball } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { friendlySnowballError } from '@/features/workspace-search/snowballText'
import { defaultFolded } from './layout'
import { SidePanel } from './SidePanel'
import { SnowballNext } from './SnowballNext'
import { hiddenIds, NO_FILTERS, TreeFilters } from './TreeFilters'
import { MapView } from './MapView'
import { OutlineView } from './OutlineView'
import { RadialView } from './RadialView'
import { NavigatorView } from './navigator/NavigatorView'
import { primaryPath } from './navigator/navPath'
import { readNav, readNavPaper, writeNav } from './navigator/navUrl'
import { TreeView } from './TreeView'
import { useStoredView, ViewSwitch } from './ViewSwitch'

export function SnowballTreeTab({ workspaceId }: { workspaceId: string }) {
  const { data, isPending, error } = useProvenance(workspaceId)
  const [stored, setView] = useStoredView(workspaceId)
  const [hasNav, setHasNav] = useState(() => readNav() !== '' || readNavPaper() !== '') // a shared walk opens in Navigate whatever is stored
  const view = hasNav ? 'navigate' : stored
  const [selected, setSelected] = useState<string | null>(null)
  const runs = useSearchRuns(workspaceId).data
  const runLabels = useMemo(() => Object.fromEntries((runs ?? []).map((r) => [r.id, r.query_text])), [runs])
  const [flipped, setFlipped] = useState<Set<string>>(new Set()) // boxes the owner folded or unfolded against their default
  const [filters, setFilters] = useState(NO_FILTERS)
  const hidden = useMemo(() => (data ? hiddenIds(data, filters) : new Set<string>()), [data, filters])
  const filterKey = JSON.stringify(filters)
  // The default folds are worked out once per filter state, so a search that grows past 12 papers on a refetch does not fold under the user.
  const baseFold = useRef<{ key: string; set: Set<string> } | null>(null)
  const folded = useMemo(() => {
    if (data && baseFold.current?.key !== filterKey) baseFold.current = { key: filterKey, set: defaultFolded(data, hidden.size > 0) }
    const base = baseFold.current?.set ?? new Set<string>()
    return new Set([...base, ...flipped].filter((id) => base.has(id) !== flipped.has(id)))
  }, [data, hidden, flipped, filterKey])
  // Hand-folded boxes are relative to the default, which depends on whether a filter is on; a filter change starts over.
  const changeFilters = (f: typeof NO_FILTERS) => { setFilters(f); setFlipped(new Set()) }
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
      else setFlipped(flip)
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

  const navigateFrom = (id: string) => {
    if (!data) return
    writeNav(primaryPath(data, id))
    setHasNav(true)
  }

  if (isPending) return <p className="text-sm text-muted-foreground">Loading the tree…</p>
  if (error || !data) return <p role="alert" className="text-sm text-destructive">Could not load the snowball tree.</p>
  if (data.roots.length === 0 && !hasNav) return <p className="text-sm text-muted-foreground">Nothing to draw yet. Run a search first.</p>

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {view !== 'navigate' && <SnowballNext workspaceId={workspaceId} />}
      <ViewSwitch value={view} onChange={(v) => {
        if (v === view) return // re-clicking the current view keeps a shared nav and the stored choice
        if (view === 'navigate') writeNav([])
        setHasNav(false)
        setView(v)
      }} />
      {view !== 'navigate' && <div className="flex flex-wrap items-center gap-3">
        <TreeFilters data={data} value={filters} onChange={changeFilters} runLabels={runLabels} />
        {view === 'tree' && stopped.size > 0 && (
          <Button type="button" size="sm" variant="outline" aria-pressed={showStopped} onClick={() => setShowStopped((v) => !v)}>
            {showStopped ? 'Hide stopped' : 'Show stopped'}
          </Button>
        )}
      </div>}
      {snowball.isError && <p role="alert" className="text-sm text-destructive">{friendlySnowballError(snowball.error.message)}</p>}
      {data.truncated && <p className="text-xs text-muted-foreground">Showing the first part of a large tree.</p>}
      <div className="flex min-h-0 flex-1 gap-3">
        {view === 'navigate' && <NavigatorView workspaceId={workspaceId} data={data} />}
        {view === 'tree' && <TreeView data={data} selected={selected} onSelect={setSelected} folded={effectiveFolded} onToggleFold={toggleFold} hidden={hidden} snowballing={busy} filterKey={filterKey} />}
        {view === 'radial' && <RadialView data={data} selected={selected} onSelect={setSelected} hidden={hidden} />}
        {view === 'map' && <MapView data={data} selected={selected} onSelect={setSelected} hidden={hidden} />}
        {view === 'outline' && <OutlineView workspaceId={workspaceId} data={data} selected={selected} onSelect={setSelected} hidden={hidden} />}
        {view !== 'navigate' && selected && <SidePanel workspaceId={workspaceId} data={data} id={selected} busy={busy === selected} onFind={find} onNavigate={navigateFrom} />}
      </div>
    </div>
  )
}
