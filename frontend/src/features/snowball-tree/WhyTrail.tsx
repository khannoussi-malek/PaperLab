import { usePaths, useProvenance } from '@/api/queries'
import { PARENT_NOT_RECORDED, isUnknown } from './layout'

const ARROW: Record<string, string> = { cites: '(it cites)', cited_by: '(cited by)' }

/** "Why is this here?": the shortest path from a search to this paper, and how many other paths lead here. */
export function WhyTrail({ workspaceId, hitId }: { workspaceId: string; hitId: string }) {
  const paths = usePaths(workspaceId, hitId).data
  const prov = useProvenance(workspaceId).data
  if (!paths || paths.length === 0) return null
  const name = (id: string) =>
    isUnknown(id) ? PARENT_NOT_RECORDED : (prov?.roots.find((r) => r.id === id)?.label ?? prov?.nodes.find((n) => n.id === id)?.title ?? 'a paper')
  const [first, ...others] = paths
  const steps = [name(first[0].parent)]
  for (const l of first) {
    if (ARROW[l.kind]) steps.push(ARROW[l.kind])
    steps.push(l.child === hitId ? 'this paper' : name(l.child))
  }
  return (
    <div role="region" aria-label="Why is this here?" className="text-xs">
      <p className="font-medium">Why is this here?</p>
      <p className="mt-0.5 text-muted-foreground">{steps.join(' → ')}</p>
      {others.length > 0 && (
        <p className="text-muted-foreground">also reached by {others.length} other path{others.length === 1 ? '' : 's'}</p>
      )}
    </div>
  )
}
