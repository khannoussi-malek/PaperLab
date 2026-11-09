import { useEffect, useRef, useState } from 'react'
import { sileo } from 'sileo'
import type { ProvenanceOut, ProvNode } from '@/api/client'
import { useWorkspacePapers } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { AskPanel } from './AskPanel'
import { Breadcrumb } from './Breadcrumb'
import { NextPapers } from './NextPapers'
import { parseNav, primaryPath, viaOf, type NavEntry } from './navPath'
import { readNav, readNavPaper, writeNav } from './navUrl'
import { PaperCard } from './PaperCard'
import { StartFromPaper } from './StartFromPaper'
import { useGrab } from './useGrab'

/** The walk to a library paper: its tree node's primary path, else the hand-added root. */
export function pathToPaper(data: ProvenanceOut, paperId: string): NavEntry[] {
  const hitPath = primaryPath(data, paperId) // the param may also name a hit (Search & screen's "Navigate from here")
  if (hitPath.length) return hitPath
  const node = data.nodes.find((n) => n.paper_id === paperId && !n.id.startsWith('paper:')) ?? data.nodes.find((n) => n.id === `paper:${paperId}`)
  const found = node ? primaryPath(data, node.id) : []
  return found.length ? found : [{ id: 'root:hand', via: 'hand' }, { id: `paper:${paperId}`, via: 'hand' }]
}

const STALE = 'This path changed; showing the part that still exists.'

/** Walks the snowball one paper at a time. The path is the only thing that moves the walk; data refetches never touch it. */
export function NavigatorView({ workspaceId, data }: { workspaceId: string; data: ProvenanceOut }) {
  const initial = useRef<ReturnType<typeof parseNav> & { fromPaper?: boolean }>(undefined)
  if (!initial.current) {
    const paperId = readNavPaper()
    initial.current = paperId ? { path: pathToPaper(data, paperId), cut: false, fromPaper: true } : parseNav(readNav(), data)
  }
  const [path, setPath] = useState<NavEntry[]>(initial.current.path)
  const [moved, setMoved] = useState(false) // the card takes focus after the owner moves, not when the page loads
  const { grabs, grab } = useGrab(workspaceId)
  const nextRef = useRef<HTMLDivElement>(null)
  const currentRef = useRef<string | undefined>(undefined)
  const reveal = (forId: string) => { // after a click only, and only while that paper is still the one on the card
    if (forId !== currentRef.current) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    nextRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
    nextRef.current?.querySelector<HTMLElement>('[role="tab"]')?.focus({ preventScroll: true })
  }
  const library = useWorkspacePapers(workspaceId).data
  useEffect(() => {
    if (initial.current?.fromPaper) writeNav(initial.current.path)
    if (!initial.current?.cut) return
    sileo.info({ title: STALE })
    writeNav(initial.current.path)
  }, [])

  useEffect(() => { // a paper entry that is no library paper and no tree node (a hit that left the tree) is stale, from navPaper or from nav
    const last = path[path.length - 1]?.id
    if (moved || !last?.startsWith('paper:') || !library || data.nodes.some((n) => n.id === last) || library.some((p) => `paper:${p.id}` === last)) return
    const fromPaper = initial.current?.fromPaper ?? false
    initial.current = { ...initial.current!, fromPaper: false }
    const kept: NavEntry[] = fromPaper ? [] : [{ id: 'root:hand', via: 'hand' }]
    sileo.info({ title: STALE })
    setPath(kept)
    writeNav(kept)
  }, [library, data, moved, path])

  const go = (next: NavEntry[]) => { setPath(next); setMoved(true); writeNav(next) }
  const stepIn = (parentId: string, childId: string, kind: string) => {
    const base = path[path.length - 1]?.id === parentId ? path : [{ id: parentId, via: 'search' as const }]
    go([...base, { id: childId, via: viaOf(kind) }])
  }

  const currentId = path[path.length - 1]?.id
  currentRef.current = currentId
  const isRoot = currentId?.startsWith('root:') ?? false
  const libraryPaper = currentId?.startsWith('paper:') ? library?.find((p) => `paper:${p.id}` === currentId) : undefined
  const node: ProvNode | null = !currentId || isRoot ? null
    : (data.nodes.find((n) => n.id === currentId)
      ?? (currentId.startsWith('paper:') ? { id: currentId, title: libraryPaper?.title ?? 'a paper', level: 0, snowballed: [], paths: 0, paper_id: currentId.slice(6) } : null))
  const crumbData = node && !data.nodes.includes(node) ? { ...data, nodes: [...data.nodes, node] } : data // a library paper off the tree still gets its name
  const lists = { workspaceId, data, onStep: stepIn, grab, grabs }

  return (
    <div className="flex min-h-0 flex-1 gap-3">
      <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-auto">
        {path.length > 0 && (
          <div className="flex items-center gap-2">
            <Button type="button" size="xs" variant="ghost" onClick={() => go([])}>All searches</Button>
            <Breadcrumb path={path} data={crumbData} onGo={(i) => go(path.slice(0, i + 1))} />
          </div>
        )}
        {path.length === 0 && (
          <>
            <StartFromPaper workspaceId={workspaceId} data={data} onPick={go} />
            {data.roots.map((r) => (
              <section key={r.id} className="flex flex-col gap-2">
                <h3 className="text-sm font-medium">{`🔍 ${r.label}`}</h3>
                <NextPapers {...lists} parentId={r.id} />
              </section>
            ))}
          </>
        )}
        {node && <PaperCard key={node.id} focusHeading={moved} workspaceId={workspaceId} data={data} node={node} grab={grab} grabs={grabs} onReveal={() => reveal(node.id)} />}
        {currentId && (isRoot || node) && <div ref={nextRef}><NextPapers {...lists} parentId={currentId} dimmed={node?.branch?.state === 'stopped'} /></div>}
      </div>
      {node && <AskPanel workspaceId={workspaceId} node={node} />}
    </div>
  )
}
