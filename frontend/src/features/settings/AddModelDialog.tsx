import { useState } from 'react'
import type { LLMConnection } from '@/api/client'
import { useAvailableModels, useConnectionMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

type Props = {
  connection: LLMConnection
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Search the provider's own model list, or type any name by hand, and add it to chat. Follows AddPapersDialog. */
export function AddModelDialog({ connection, open, onOpenChange }: Props) {
  const available = useAvailableModels(connection.id, open)
  const { addModel } = useConnectionMutations()
  const [search, setSearch] = useState('')

  const listed = new Set(connection.models.map((model) => model.name))
  const noList = !available.isPending && !available.isError && available.data?.models === null
  const candidates = (available.data?.models ?? []).filter((name) => !listed.has(name))
  const typed = search.trim()
  const visibleCandidates = candidates.filter((name) => typed === '' || name.toLowerCase().includes(typed.toLowerCase()))
  const offerTyped = typed !== '' && !listed.has(typed) && !candidates.includes(typed)

  function close() {
    setSearch('')
    addModel.reset()
    onOpenChange(false)
  }

  async function add(name: string) {
    await addModel.mutateAsync({ connectionId: connection.id, name })
    close()
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>Add a model</DialogTitle>
        </DialogHeader>
        <Command className="bg-transparent p-0" shouldFilter={false}>
          <CommandInput
            aria-label="Search or type a model name"
            placeholder="Search or type a model name…"
            value={search}
            onValueChange={setSearch}
          />
          {noList && <p className="px-3 pt-2 text-xs text-muted-foreground">No model list here; type model names by hand</p>}
          <CommandList>
            <CommandEmpty>{available.isPending ? 'Loading models…' : noList ? 'Type a name above to add it.' : 'No matching models.'}</CommandEmpty>
            {!available.isPending &&
              visibleCandidates.map((name) => (
                <CommandItem key={name} value={name} onSelect={() => void add(name)}>
                  {name}
                </CommandItem>
              ))}
            {offerTyped && (
              <CommandItem value={`add:${typed}`} onSelect={() => void add(typed)}>
                Add “{typed}”
              </CommandItem>
            )}
          </CommandList>
        </Command>
        {available.isError && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{available.error.message}</AlertDescription>
          </Alert>
        )}
        {addModel.error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{addModel.error.message}</AlertDescription>
          </Alert>
        )}
      </DialogContent>
    </Dialog>
  )
}
