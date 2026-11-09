import { useState } from 'react'
import type { ProvenanceOut } from '@/api/client'
import { useWorkspacePapers } from '@/api/queries'
import { primaryPath, type NavEntry } from './navPath'

const MAX = 10

type Match = { key: string; title: string; year?: number | null; path: NavEntry[] }

/** "Start from a paper": type part of a title, pick a paper from the tree or the library, and the walk starts on it. */
export function StartFromPaper({ workspaceId, data, onPick }: { workspaceId: string; data: ProvenanceOut; onPick: (path: NavEntry[]) => void }) {
  const [query, setQuery] = useState('')
  const library = useWorkspacePapers(workspaceId).data ?? []
  const q = query.trim().toLowerCase()
  const onTree = new Set(data.nodes.map((n) => n.paper_id).filter(Boolean))
  const hand = (paperId: string): NavEntry[] => [{ id: 'root:hand', via: 'hand' }, { id: `paper:${paperId}`, via: 'hand' }]
  const offTree = q === '' ? [] : library.filter((p) => !onTree.has(p.id) && p.title.toLowerCase().includes(q))
  const onTreeAll = q === '' ? [] : data.nodes.filter((n) => n.title.toLowerCase().includes(q))
  const cut = offTree.length > MAX || onTreeAll.length > MAX
  const matches: Match[] = [
    ...offTree.slice(0, MAX).map((p) => ({ key: `paper:${p.id}`, title: p.title, year: p.year, path: hand(p.id) })),
    ...onTreeAll.slice(0, MAX).map((n) => {
      const path = primaryPath(data, n.id)
      return { key: n.id, title: n.title, year: n.year, path: path.length === 0 && n.paper_id ? hand(n.paper_id) : path }
    }),
  ]
  return (
    <div className="flex flex-col gap-1">
      <label className="text-sm font-medium" htmlFor="start-from-paper">Start from a paper</label>
      <input id="start-from-paper" className="rounded-md border border-border bg-background px-2 py-1 text-sm" placeholder="Type part of a title" value={query} onChange={(e) => setQuery(e.target.value)} />
      {q !== '' && matches.length === 0 && <p className="text-xs text-muted-foreground">No paper has that in its title.</p>}
      {cut && <p className="text-xs text-muted-foreground">More matches: keep typing</p>}
      {matches.length > 0 && (
        <ul className="flex flex-col rounded-md border border-border">
          {matches.map((m) => (
            <li key={m.key}>
              <button type="button" className="w-full truncate px-2 py-1 text-left text-sm hover:bg-muted" onClick={() => { setQuery(''); onPick(m.path) }}>
                {m.title}{m.year ? ` · ${m.year}` : ''}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
