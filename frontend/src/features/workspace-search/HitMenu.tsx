import { CircleHelp, CircleX, EllipsisVertical, ThumbsUp } from 'lucide-react'
import type { ReactNode } from 'react'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import type { Hit, HitReviewUpdate } from '@/api/client'

const EXCLUDE_REASONS = ['wrong_topic', 'wrong_study_type', 'duplicate', 'language', 'inaccessible', 'other'] as const

// Wider than PaperMenu's w-56: this menu also carries a title/byline/abstract preview, not just short action
// labels, so the reader has enough to judge relevance without leaving the list.
const menuSurface = cn(glass, 'w-80 bg-glass-strong ring-glass-border')

// The ⋮ dropdown and the right-click menu show the same items, built from their own Radix parts — same split as
// PaperMenu/PaperContextMenu.
const dropdownParts = {
  Item: DropdownMenuItem,
  Sub: DropdownMenuSub,
  SubTrigger: DropdownMenuSubTrigger,
  SubContent: DropdownMenuSubContent,
  Separator: DropdownMenuSeparator,
}
const contextParts = {
  Item: ContextMenuItem,
  Sub: ContextMenuSub,
  SubTrigger: ContextMenuSubTrigger,
  SubContent: ContextMenuSubContent,
  Separator: ContextMenuSeparator,
}

type Props = {
  hit: Hit
  onReview: (hitId: string, body: HitReviewUpdate) => void
}

/** Title, byline and abstract — everything the reader needs to judge relevance without leaving the list. A hit
 * whose candidate never matched an ExternalRef (title/authors/year/venue/abstract all null) falls back to the
 * normalized_title every hit always has. */
function Preview({ hit }: { hit: Hit }) {
  const byline = [hit.authors?.join(', '), hit.year, hit.venue].filter(Boolean).join(' · ')
  return (
    <div className="max-h-72 overflow-y-auto px-2 py-1.5">
      <p className="text-sm font-medium">{hit.title ?? hit.normalized_title}</p>
      {byline && <p className="text-xs text-muted-foreground">{byline}</p>}
      {hit.abstract && <p className="mt-1 text-xs">{hit.abstract}</p>}
    </div>
  )
}

function MenuItems({ parts: M, hit, onReview }: Props & { parts: typeof dropdownParts | typeof contextParts }) {
  return (
    <>
      <Preview hit={hit} />
      <M.Separator />
      <M.Item onSelect={() => onReview(hit.id, { stage1_status: 'relevant' })}>
        <ThumbsUp aria-hidden />
        Relevant
      </M.Item>
      <M.Item onSelect={() => onReview(hit.id, { stage1_status: 'maybe' })}>
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
            <M.Item key={reason} onSelect={() => onReview(hit.id, { stage1_status: 'not_relevant', stage1_exclude_reason: reason })}>
              {reason}
            </M.Item>
          ))}
        </M.SubContent>
      </M.Sub>
    </>
  )
}

/** A hit row's ⋮ menu: title/byline/abstract preview, then stage-1 triage (relevant / maybe / not relevant). */
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
