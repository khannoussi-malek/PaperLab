import { ChevronDown } from 'lucide-react'
import type { ReviewRun } from '@/api/client'
import { Button } from '@/components/ui/button'
import { isLive } from './reviewModel'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

const NO_WORKSPACE = 'Pick a workspace first'

/** The editor toolbar's Review button, and the run's progress line while a check is live. */
export function ReviewMenu({ hasWorkspace, run, onCheck, onCancel }: {
  hasWorkspace: boolean
  run: Pick<ReviewRun, 'status' | 'done' | 'total'> | null
  onCheck: () => void
  onCancel: () => void
}) {
  return (
    <>
      {isLive(run) && (
        <span className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
          Checking {run!.done} of {run!.total}…
          <Button size="xs" variant="ghost" onClick={onCancel}>Cancel</Button>
        </span>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="outline">Review<ChevronDown aria-hidden /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem disabled={!hasWorkspace || isLive(run)} onSelect={onCheck}>Check citations</DropdownMenuItem>
          {!hasWorkspace && <p className="px-2 py-1 text-xs text-muted-foreground">{NO_WORKSPACE}</p>}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  )
}
