import { type FormEvent, useState } from 'react'
import type { GraphNode } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { glass } from '@/components/glass'
import { cn } from '@/lib/utils'
import { LABEL_MAX_CHARS, labelError } from './graphModel'

export type LinkDraft = { toPaper: string; label: string }

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The paper the link starts at, or the one being renamed. */
  fromTitle: string
  /** The papers the link can point at; empty while editing an existing link's label. */
  choices: GraphNode[]
  /** Set when editing: the dialog then only asks for a new label. */
  editing: { label: string; toTitle: string } | null
  pending: boolean
  error: string | null
  onSubmit: (draft: LinkDraft) => void
}

export function LinkDialog({ open, onOpenChange, fromTitle, choices, editing, pending, error, onSubmit }: Props) {
  const [toPaper, setToPaper] = useState('')
  const [label, setLabel] = useState(editing?.label ?? '')
  const [touched, setTouched] = useState(false)
  const invalid = labelError(label)
  const missingPaper = editing === null && toPaper === ''

  function submit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (pending) return
    if (invalid || missingPaper) return
    onSubmit({ toPaper, label: label.trim() })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setToPaper('')
          setLabel(editing?.label ?? '')
          setTouched(false)
        }
        onOpenChange(next)
      }}
    >
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit label' : 'Link to another paper'}</DialogTitle>
          <DialogDescription>
            {editing
              ? `Your link from "${fromTitle}" to "${editing.toTitle}".`
              : `Draw your own link from "${fromTitle}", and say what it means.`}
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          {editing === null && (
            <div className="flex flex-col gap-2">
              {/* cmdk overwrites any id passed to CommandInput, so a <Label htmlFor> would bind to nothing. The
                  caption is plain text, and `label` fills cmdk's own hidden <label>, which does bind. */}
              <p className="text-sm leading-none font-medium">Paper to link to</p>
              <Command label="Paper to link to" className="rounded-lg border border-input bg-transparent">
                <CommandInput aria-label="Paper to link to" placeholder="Search your papers" />
                <CommandList className="max-h-56">
                  <CommandEmpty>No paper matches.</CommandEmpty>
                  {choices.map((paper) => (
                    <CommandItem
                      key={paper.id}
                      value={`${paper.title} ${paper.id}`}
                      data-paper-id={paper.id}
                      data-selected-paper={paper.id === toPaper}
                      onSelect={() => setToPaper(paper.id)}
                    >
                      <span className="truncate" title={paper.title}>
                        {paper.title}
                      </span>
                      {paper.year !== null && <span className="ml-auto text-muted-foreground">{paper.year}</span>}
                    </CommandItem>
                  ))}
                </CommandList>
              </Command>
              {touched && missingPaper && <p className="text-sm text-destructive">Choose a paper to link to.</p>}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="link-label">Label</Label>
            <Input
              id="link-label"
              value={label}
              placeholder="builds on"
              maxLength={LABEL_MAX_CHARS}
              onChange={(event) => setLabel(event.target.value)}
            />
            {touched && invalid && <p className="text-sm text-destructive">{invalid}</p>}
          </div>

          {error && <ErrorAlert message={error} />}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? 'Saving…' : 'Save link'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
