import { useState } from 'react'
import { useApplyTag, usePaperTags, useRemoveTag, useTags } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { tagErrorText } from './tagErrors'

type Props = { workspaceId: string; mode: 'add' | 'remove'; paperIds: string[]; onDone: () => void }

/** Adds a tag (an existing one, or a new one typed in) to the given papers, or removes one they carry. */
export function TagPicker({ workspaceId, mode, paperIds, onDone }: Props) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const tags = useTags(workspaceId).data ?? []
  const paperTags = usePaperTags(workspaceId).data ?? {}
  const apply = useApplyTag(workspaceId)
  const remove = useRemoveTag(workspaceId)
  const action = mode === 'add' ? apply : remove

  const present = new Set(paperIds.flatMap((id) => paperTags[id] ?? []))
  const names = tags.map((t) => t.name).filter((name) => mode === 'add' || present.has(name))
  const needle = text.trim().toLowerCase()
  const shown = names.filter((name) => name.toLowerCase().includes(needle))
  const canCreate = mode === 'add' && needle !== '' && !tags.some((t) => t.name.toLowerCase() === needle)

  function choose(tag: string) {
    action.mutate(
      { tag, paperIds },
      {
        onSuccess: () => {
          setOpen(false)
          setText('')
          onDone()
        },
      },
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">{mode === 'add' ? 'Tag…' : 'Remove tag…'}</Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64">
        {/* The list is filtered here, not by cmdk, so "Create" stays visible whatever is typed. */}
        <Command shouldFilter={false} label="Tag name">
          <CommandInput placeholder={mode === 'add' ? 'Find or create a tag' : 'Find a tag'} value={text} onValueChange={setText} />
          <CommandList>
            <CommandGroup>
              {shown.map((name) => (
                <CommandItem key={name} value={name} onSelect={() => choose(name)}>
                  {name}
                </CommandItem>
              ))}
              {canCreate && (
                <CommandItem value={`create:${needle}`} onSelect={() => choose(text.trim())}>
                  Create "{text.trim()}"
                </CommandItem>
              )}
            </CommandGroup>
          </CommandList>
        </Command>
        {action.error && <p role="alert" className="text-sm text-destructive">{tagErrorText(action.error.message)}</p>}
      </PopoverContent>
    </Popover>
  )
}
