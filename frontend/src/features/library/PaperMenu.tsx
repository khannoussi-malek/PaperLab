import { EllipsisVertical, FolderMinus, FolderPlus } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Paper } from '@/api/client'
import { useWorkspaces } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuCheckboxItem,
  ContextMenuContent,
  ContextMenuItem,
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
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
}
const contextParts = {
  Item: ContextMenuItem,
  CheckboxItem: ContextMenuCheckboxItem,
  Sub: ContextMenuSub,
  SubTrigger: ContextMenuSubTrigger,
  SubContent: ContextMenuSubContent,
}

type Props = {
  paper: Paper
  /** The workspace being shown, if any: its row also offers "Remove from workspace". */
  workspaceId?: string
  onMembershipChange: (workspaceId: string, member: boolean) => void
}

function MenuItems({ parts: M, paper, workspaceId, onMembershipChange }: Props & { parts: typeof dropdownParts | typeof contextParts }) {
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
    <DropdownMenu>
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
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className={menuSurface}>
        <MenuItems parts={contextParts} {...props} />
      </ContextMenuContent>
    </ContextMenu>
  )
}
