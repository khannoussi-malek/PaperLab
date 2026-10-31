import { ChevronDown } from 'lucide-react'
import type { ReviewRun } from '@/api/client'
import { Button } from '@/components/ui/button'
import { isLive } from './reviewModel'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'

const NO_WORKSPACE = 'Pick a workspace first'

/** The editor toolbar's Review button, and the run's progress line while a check is live. */
export function ReviewMenu({ hasWorkspace, run, onCheck, onCancel, onReviewSection, sectionLive = false }: {
  hasWorkspace: boolean
  run: Pick<ReviewRun, 'status' | 'done' | 'total'> | null
  onCheck: () => void
  onCancel: () => void
  /** Review → Review this section (no workspace needed: the notes are just left out). */
  onReviewSection?: () => void
  /** A section review is queued or running for this file. */
  sectionLive?: boolean
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
          {onReviewSection && <DropdownMenuItem disabled={sectionLive} onSelect={onReviewSection}>Review this section</DropdownMenuItem>}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  )
}
