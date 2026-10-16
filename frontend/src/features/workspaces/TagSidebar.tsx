import { useId } from 'react'
import { useTags } from '@/api/queries'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import type { TagMatch } from '@/lib/route'
import { plural } from '@/features/charts/chartMeta'
import { cn } from '@/lib/utils'
import { TagActionsMenu } from './TagActionsMenu'
import { coverageText, toggled } from './tagFilter'

export type TagFilterProps = {
  workspaceId: string
  selected: string[]
  match: TagMatch
  onChange: (selected: string[], match: TagMatch) => void
}

/** The wide-screen tag filter: every tag of the workspace with its paper count, and the any/all switch. */
export function TagSidebar({ workspaceId, selected, match, onChange }: TagFilterProps) {
  const tags = useTags(workspaceId).data ?? []
  const switchId = useId()
  return (
    <aside className="hidden w-52 shrink-0 space-y-2 lg:block">
      <h2 className="font-heading text-sm font-semibold">Tags</h2>
      {tags.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tags yet. Select papers and choose Tag… to add one.</p>
      ) : (
        <TooltipProvider>
          <ul className="flex flex-col gap-0.5">
            {tags.map((tag) => (
              <li key={tag.id} className="flex items-center gap-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      aria-label={`${tag.name}, ${plural(tag.papers, 'paper')}`}
                      aria-pressed={selected.includes(tag.name)}
                      onClick={() => onChange(toggled(selected, tag.name), match)}
                      className={cn(
                        'flex min-w-0 flex-1 items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-foreground/5',
                        selected.includes(tag.name) && 'bg-primary/10 font-medium',
                      )}
                    >
                      <span className="truncate">{tag.name}</span>
                      <span className="text-muted-foreground tabular-nums">{tag.papers}</span>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">{coverageText(tag)}</TooltipContent>
                </Tooltip>
                <TagActionsMenu
                  workspaceId={workspaceId}
                  tag={tag}
                  onRenamed={(from, to) => onChange(selected.map((t) => (t === from ? to : t)), match)}
                  onDeleted={(name) => selected.includes(name) && onChange(selected.filter((t) => t !== name), match)}
                />
              </li>
            ))}
          </ul>
        </TooltipProvider>
      )}
      <div className="flex items-center gap-2">
        <Switch id={switchId} size="sm" checked={match === 'all'} onCheckedChange={(on) => onChange(selected, on ? 'all' : 'any')} />
        <Label htmlFor={switchId} className="text-sm font-normal">Match all</Label>
      </div>
    </aside>
  )
}
