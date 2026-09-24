import { CircleHelp, CircleX, EllipsisVertical, ThumbsUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import type { HitReviewUpdate } from '@/api/client'

const EXCLUDE_REASONS = ['wrong_topic', 'wrong_study_type', 'duplicate', 'language', 'inaccessible', 'other'] as const

const menuSurface = cn(glass, 'w-56 bg-glass-strong ring-glass-border')

// The ⋮ dropdown and the right-click menu show the same items, built from their own Radix parts — same split as
// PaperMenu/PaperContextMenu.
const dropdownParts = { Item: DropdownMenuItem, Sub: DropdownMenuSub, SubTrigger: DropdownMenuSubTrigger, SubContent: DropdownMenuSubContent }
const contextParts = { Item: ContextMenuItem, Sub: ContextMenuSub, SubTrigger: ContextMenuSubTrigger, SubContent: ContextMenuSubContent }

type Props = {
  hitId: string
  onReview: (hitId: string, body: HitReviewUpdate) => void
}

function MenuItems({ parts: M, hitId, onReview }: Props & { parts: typeof dropdownParts | typeof contextParts }) {
  return (
    <>
      <M.Item onSelect={() => onReview(hitId, { stage1_status: 'relevant' })}>
        <ThumbsUp aria-hidden />
        Relevant
      </M.Item>
      <M.Item onSelect={() => onReview(hitId, { stage1_status: 'maybe' })}>
        <CircleHelp aria-hidden />
        Maybe
      </M.Item>
      <M.Sub>
        <M.SubTrigger>
          <CircleX aria-hidden />
          Not relevant…
        </M.SubTrigger>
        <M.SubContent className={menuSurface}>
          {EXCLUDE_REASONS.map((reason) => (
            <M.Item key={reason} onSelect={() => onReview(hitId, { stage1_status: 'not_relevant', stage1_exclude_reason: reason })}>
              {reason}
            </M.Item>
          ))}
        </M.SubContent>
      </M.Sub>
    </>
  )
}

/** A hit row's ⋮ menu: stage-1 triage (relevant / maybe / not relevant, with a reason). */
export function HitMenu(props: Props) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Hit actions"
          title="Hit actions"
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
export function HitContextMenu({ children, ...props }: Props & { children: ReactNode }) {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className={menuSurface}>
        <MenuItems parts={contextParts} {...props} />
      </ContextMenuContent>
    </ContextMenu>
  )
}
