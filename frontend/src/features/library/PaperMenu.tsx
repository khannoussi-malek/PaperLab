import { EllipsisVertical, FolderMinus, FolderPlus } from 'lucide-react'
import type { Paper } from '@/api/client'
import { useWorkspaces } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
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

type Props = {
  paper: Paper
  /** The workspace being shown, if any: its row also offers "Remove from workspace". */
  workspaceId?: string
  /** Controlled by the row, which also opens the menu on right-click. */
  open: boolean
  onOpenChange: (open: boolean) => void
  onMembershipChange: (workspaceId: string, member: boolean) => void
}

/** A paper row's menu: workspaces with check marks that toggle membership. */
export function PaperMenu({ paper, workspaceId, open, onOpenChange, onMembershipChange }: Props) {
  const workspaces = useWorkspaces()
  // The API already orders workspaces by name (Postgres collation); no client re-sort.
  const sorted = workspaces.data ?? []
  return (
    <DropdownMenu open={open} onOpenChange={onOpenChange}>
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
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <FolderPlus aria-hidden />
            Add to workspace…
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className={menuSurface}>
            {sorted.length === 0 && <DropdownMenuItem disabled>No workspaces yet</DropdownMenuItem>}
            {sorted.map((workspace) => (
              <DropdownMenuCheckboxItem
                key={workspace.id}
                checked={paper.workspace_ids.includes(workspace.id)}
                // Stays open, so several workspaces can be ticked in one go.
                onSelect={(event) => event.preventDefault()}
                onCheckedChange={(checked) => onMembershipChange(workspace.id, checked)}
              >
                {workspace.name}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        {workspaceId && (
          <DropdownMenuItem onSelect={() => onMembershipChange(workspaceId, false)}>
            <FolderMinus aria-hidden />
            Remove from workspace
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
