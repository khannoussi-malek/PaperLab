import { usePaperTagGroups } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { workspaceHref } from '@/lib/route'

/** A paper's tags, grouped by workspace; each chip opens that workspace's papers filtered by the tag. */
export function PaperTagChips({ paperId }: { paperId: string }) {
  const groups = usePaperTagGroups(paperId).data ?? []
  if (groups.length === 0) return null
  return (
    <>
      {groups.map((group) => (
        <span key={group.workspace_id} className="flex shrink-0 flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">{group.workspace_name}</span>
          {group.tags.map((name) => (
            <a
              key={name}
              href={workspaceHref(group.workspace_id, 'papers', undefined, { tags: [name], match: 'any' })}
              aria-label={`Show papers tagged ${name} in ${group.workspace_name}`}
              className="rounded-md focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <Badge variant="outline" className="font-normal">{name}</Badge>
            </a>
          ))}
        </span>
      ))}
    </>
  )
}
