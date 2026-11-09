import { useEffect, useRef, useState } from 'react'
import { sileo } from 'sileo'
import type { ProvenanceOut, ProvNode } from '@/api/client'
import { useWorkspacePapers } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Breadcrumb } from './Breadcrumb'
import { NextPapers } from './NextPapers'
import { parseNav, primaryPath, viaOf, type NavEntry } from './navPath'
import { readNav, readNavPaper, writeNav } from './navUrl'
import { PaperCard } from './PaperCard'
import { StartFromPaper } from './StartFromPaper'
import { useGrab } from './useGrab'

/** The walk to a library paper: its tree node's primary path, else the hand-added root. */
export function pathToPaper(data: ProvenanceOut, paperId: string): NavEntry[] {
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
  const { grabs, grab } = useGrab(workspaceId)
  const library = useWorkspacePapers(workspaceId).data
  useEffect(() => {
    if (initial.current?.fromPaper) writeNav(initial.current.path)
    if (!initial.current?.cut) return
    sileo.info({ title: STALE })
    writeNav(initial.current.path)
  }, [])

  const go = (next: NavEntry[]) => { setPath(next); writeNav(next) }
  const stepIn = (parentId: string, childId: string, kind: string) => {
    const base = path[path.length - 1]?.id === parentId ? path : [{ id: parentId, via: 'search' as const }]
    go([...base, { id: childId, via: viaOf(kind) }])
  }

  const currentId = path[path.length - 1]?.id
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
        {node && <PaperCard key={node.id} workspaceId={workspaceId} data={data} node={node} grab={grab} grabs={grabs} />}
        {currentId && (isRoot || node) && <NextPapers {...lists} parentId={currentId} dimmed={node?.branch?.state === 'stopped'} />}
      </div>
      {/* The Ask the AI panel docks here (Task 5). */}
    </div>
  )
}
