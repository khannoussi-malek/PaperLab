import { BookOpenCheck, EllipsisVertical, FolderMinus, FolderPlus } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Paper, ReadingIn } from '@/api/client'
import { useWorkspaces } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuCheckboxItem,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuRadioGroup,
  ContextMenuRadioItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { LEVELS, TRIAGES, UNDECIDED_LABEL, type Triage } from '@/features/reading/passes'
import { cn } from '@/lib/utils'

// Wide enough for "Add to workspace…" and a typical workspace name on one line.
const menuSurface = cn(glass, 'w-56 bg-glass-strong ring-glass-border')

// The ⋮ dropdown and the right-click menu show the same items, built from their own Radix parts.
const dropdownParts = {
  Item: DropdownMenuItem,
  CheckboxItem: DropdownMenuCheckboxItem,
  Sub: DropdownMenuSub,
  SubTrigger: DropdownMenuSubTrigger,
  SubContent: DropdownMenuSubContent,
  RadioGroup: DropdownMenuRadioGroup,
  RadioItem: DropdownMenuRadioItem,
  Label: DropdownMenuLabel,
  Separator: DropdownMenuSeparator,
}
const contextParts = {
  Item: ContextMenuItem,
  CheckboxItem: ContextMenuCheckboxItem,
  Sub: ContextMenuSub,
  SubTrigger: ContextMenuSubTrigger,
  SubContent: ContextMenuSubContent,
  RadioGroup: ContextMenuRadioGroup,
  RadioItem: ContextMenuRadioItem,
  Label: ContextMenuLabel,
  Separator: ContextMenuSeparator,
}

type Props = {
  paper: Paper
  /** The workspace being shown, if any: its row also offers "Remove from workspace". */
  workspaceId?: string
  onMembershipChange: (workspaceId: string, member: boolean) => void
  onReadingChange: (changes: ReadingIn) => void
}

function MenuItems({ parts: M, paper, workspaceId, onMembershipChange, onReadingChange }: Props & { parts: typeof dropdownParts | typeof contextParts }) {
  const workspaces = useWorkspaces()
  // The API already orders workspaces by name (Postgres collation); no client re-sort.
  const sorted = workspaces.data ?? []
  return (
    <>
      <M.Sub>
        <M.SubTrigger>
          <FolderPlus aria-hidden />
          Add to workspace…
        </M.SubTrigger>
        <M.SubContent className={menuSurface}>
          {sorted.length === 0 && <M.Item disabled>No workspaces yet</M.Item>}
          {sorted.map((workspace) => (
            <M.CheckboxItem
              key={workspace.id}
              checked={paper.workspace_ids.includes(workspace.id)}
              // Stays open, so several workspaces can be ticked in one go.
              onSelect={(event) => event.preventDefault()}
              onCheckedChange={(checked) => onMembershipChange(workspace.id, checked)}
            >
              {workspace.name}
            </M.CheckboxItem>
          ))}
        </M.SubContent>
      </M.Sub>
      <M.Sub>
        <M.SubTrigger>
          <BookOpenCheck aria-hidden />
          Reading
        </M.SubTrigger>
        <M.SubContent className={menuSurface}>
          <M.Label>Passes finished</M.Label>
          <M.RadioGroup
            value={String(paper.reading_pass)}
            onValueChange={(value) => onReadingChange({ reading_pass: Number(value) })}
          >
            {LEVELS.map((level) => (
              <M.RadioItem key={level.value} value={String(level.value)} onSelect={(event) => event.preventDefault()}>
                {level.label}
              </M.RadioItem>
            ))}
          </M.RadioGroup>
          <M.Separator />
          <M.Label>Decision</M.Label>
          <M.RadioGroup
            value={paper.triage ?? 'undecided'}
            onValueChange={(value) => onReadingChange({ triage: value === 'undecided' ? null : (value as Triage) })}
          >
            {[...TRIAGES, { value: 'undecided' as const, label: UNDECIDED_LABEL }].map((option) => (
              <M.RadioItem key={option.value} value={option.value} onSelect={(event) => event.preventDefault()}>
                {option.label}
              </M.RadioItem>
            ))}
          </M.RadioGroup>
        </M.SubContent>
      </M.Sub>
      {workspaceId && (
        <M.Item onSelect={() => onMembershipChange(workspaceId, false)}>
          <FolderMinus aria-hidden />
          Remove from workspace
        </M.Item>
      )}
    </>
  )
}

/** A paper row's ⋮ menu: workspaces with check marks that toggle membership. */
export function PaperMenu(props: Props) {
  return (
    // Non-modal: the Reading submenu deliberately stays open across several picks (its radio items call
    // event.preventDefault() on select), and Radix's modal default would otherwise aria-hide the rest of the
    // page (hideOthers) for as long as it's open, locking out the library's own Reading filter and everything
    // else until this menu is explicitly dismissed.
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Paper actions"
          title="Paper actions"
          className="relative z-10 text-muted-foreground"
        >
          <EllipsisVertical aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className={menuSurface}>
        <MenuItems parts={dropdownParts} {...props} />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** The same menu on right-click, opened where the pointer is. `children` is the row it wraps. */
export function PaperContextMenu({ children, ...props }: Props & { children: ReactNode }) {
  return (
    // Non-modal for the same reason as PaperMenu above.
    <ContextMenu modal={false}>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className={menuSurface}>
        <MenuItems parts={contextParts} {...props} />
      </ContextMenuContent>
    </ContextMenu>
  )
}
