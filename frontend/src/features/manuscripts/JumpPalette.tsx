import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import type { Target } from './jumpTargets'

export type JumpCommand = { id: string; label: string; run: () => void }
const GROUPS: [Target['kind'], string][] = [['section', 'Sections'], ['heading', 'Headings'], ['label', 'Labels'], ['paper', 'Papers']]

/** Cmd/Ctrl+K: jump to a section, label or paper, or run a studio command. */
export function JumpPalette({ open, onOpenChange, targets, commands, onPick }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  targets: Target[]
  commands: JumpCommand[]
  onPick: (t: Target) => void
}) {
  const done = (f: () => void) => () => { onOpenChange(false); f() }
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Jump to" description="Find a section, label or paper, or run a command.">
      <Command>
        <CommandInput placeholder="Jump to a section, label or paper…" />
        <CommandList>
          <CommandEmpty>Nothing matches.</CommandEmpty>
          <CommandGroup heading="Commands">
            {commands.map((c) => <CommandItem key={c.id} value={`command ${c.label}`} onSelect={done(c.run)}>{c.label}</CommandItem>)}
          </CommandGroup>
          {GROUPS.map(([kind, heading]) => {
            const mine = targets.filter((t) => t.kind === kind)
            return mine.length > 0 && (
              <CommandGroup key={kind} heading={heading}>
                {mine.map((t) => (
                  <CommandItem key={t.id} value={`${t.label} ${t.detail} ${t.id}`} onSelect={done(() => onPick(t))}>
                    <span className="truncate">{t.label}</span>
                    {t.detail && <span className="ml-auto truncate pl-3 text-xs text-muted-foreground">{t.detail}</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            )
          })}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
