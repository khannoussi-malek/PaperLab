import { useState } from 'react'
import type { ProvLink } from '@/api/client'
import { usePaths, useProvenance } from '@/api/queries'
import { PARENT_NOT_RECORDED, isUnknown } from './layout'

const ARROW: Record<string, string> = { cites: '(it cites)', cited_by: '(cited by)' }

/** "Why is this here?": the shortest path from a search to this paper, and how many other paths lead here. */
export function WhyTrail({ workspaceId, hitId }: { workspaceId: string; hitId: string }) {
  const paths = usePaths(workspaceId, hitId).data
  const prov = useProvenance(workspaceId).data
  const [open, setOpen] = useState(false)
  if (!paths || paths.length === 0) return null
  const name = (id: string) =>
    isUnknown(id) ? PARENT_NOT_RECORDED : (prov?.roots.find((r) => r.id === id)?.label ?? prov?.nodes.find((n) => n.id === id)?.title ?? 'a paper')
  const describe = (path: ProvLink[]) => {
    const steps = [name(path[0].parent)]
    for (const l of path) {
      if (ARROW[l.kind]) steps.push(ARROW[l.kind])
      steps.push(l.child === hitId ? 'this paper' : name(l.child))
    }
    return steps.join(' → ')
  }
  const [first, ...others] = paths
  // The node's own count is the truth; `paths` is cut at the server's path limit.
  const total = Math.max((prov?.nodes.find((n) => n.id === hitId)?.paths ?? 1) - 1, others.length)
  return (
    <div role="region" aria-label="Why is this here?" className="text-xs">
      <p className="font-medium">Why is this here?</p>
      <p className="mt-0.5 text-muted-foreground">{describe(first)}</p>
      {total > 0 && (
        <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="text-muted-foreground underline underline-offset-2">
          +{total} other path{total === 1 ? '' : 's'}
        </button>
      )}
      {open && (
        <ul className="mt-1 space-y-1 text-muted-foreground">
          {others.map((p, i) => <li key={i}>{describe(p)}</li>)}
          {total > others.length && <li>…and {total - others.length} more not listed</li>}
        </ul>
      )}
    </div>
  )
}
