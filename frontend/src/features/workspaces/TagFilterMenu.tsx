import { Check, Tags } from 'lucide-react'
import { useId } from 'react'
import { useTags } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { toggled } from './tagFilter'
import type { TagFilterProps } from './TagSidebar'

/** The narrow-screen tag filter: a dropdown multi-select of the workspace's tags with counts, and the any/all switch. */
export function TagFilterMenu({ workspaceId, selected, match, onChange }: TagFilterProps) {
  const tags = useTags(workspaceId).data ?? []
  const switchId = useId()
  return (
    <div className="lg:hidden">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline">
            <Tags aria-hidden />
            Tags{selected.length > 0 && ` (${selected.length})`}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64">
          <Command>
            <CommandInput placeholder="Find a tag" />
            <CommandList>
              <CommandEmpty>No tags.</CommandEmpty>
              <CommandGroup>
                {tags.map((tag) => (
                  <CommandItem key={tag.id} value={tag.name} onSelect={() => onChange(toggled(selected, tag.name), match)}>
                    <Check aria-hidden className={cn(!selected.includes(tag.name) && 'invisible')} />
                    <span className="flex-1 truncate">{tag.name}</span>
                    <span className="text-muted-foreground tabular-nums">{tag.papers}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
          <div className="flex items-center gap-2">
            <Switch id={switchId} size="sm" checked={match === 'all'} onCheckedChange={(on) => onChange(selected, on ? 'all' : 'any')} />
            <Label htmlFor={switchId} className="text-sm font-normal">Match all</Label>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
