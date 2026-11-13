import { ChevronDown, Ellipsis } from 'lucide-react'
import { useState } from 'react'
import { Collapsible } from 'radix-ui'
import type { Role, Section } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { ROLE_LABEL } from './lenses'
import { READER_CHECKLISTS } from './readerChecklists'

const AUTOMATIC = 'automatic'
const ROLES = Object.keys(ROLE_LABEL) as Role[]

type Props = {
  section: Section
  /** A role fix is being saved: the menu's choices wait (the trigger stays enabled so focus isn't lost). */
  busy: boolean
  onJump: () => void
  /** null: back to the automatic role. Only offered on a section with a heading. */
  onRoleChange: (role: Role | null) => void
  /** Opens the AI number suggestions for this section (D33); left out when the paper has no PDF to anchor them on. */
  onSuggestNumbers?: () => void
}

/** One section in the Lens tab: its heading, role and page, a click to jump there, and ⋯ to change its role. */
export function SectionRow({ section, busy, onJump, onRoleChange, onSuggestNumbers }: Props) {
  const title = section.title ?? 'Before the first heading'
  const fixed = section.source === 'user'
  const checklist = READER_CHECKLISTS[section.role]
  return (
    <li className="lens-section flex flex-col gap-1" data-role={section.role}>
      <div className="flex items-start gap-1">
        <button
          type="button"
          className="lens-jump flex min-w-0 flex-1 flex-col items-start gap-1 rounded-md p-2 text-left outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
          onClick={onJump}
        >
          <span className="w-full truncate text-sm font-medium" title={title}>
            {title}
          </span>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Badge variant="outline" className="role-chip">
              {ROLE_LABEL[section.role]}
            </Badge>
            {fixed && (
              <span className="role-fixed">
                <span className="sr-only">fixed by </span>you
              </span>
            )}
            <span className="tabular-nums">p. {section.page}</span>
          </span>
          <span className="line-clamp-2 text-xs text-muted-foreground" title={section.preview}>
            {section.preview}
          </span>
        </button>
        {section.title !== null && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label={`Section actions for ${section.title}, page ${section.page}`}>
                <Ellipsis aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Change role</DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={fixed ? section.role : AUTOMATIC}
                onValueChange={(value) => onRoleChange(value === AUTOMATIC ? null : (value as Role))}
              >
                <DropdownMenuRadioItem value={AUTOMATIC} disabled={busy}>Automatic</DropdownMenuRadioItem>
                <DropdownMenuSeparator />
                {ROLES.map((role) => (
                  <DropdownMenuRadioItem key={role} value={role} disabled={busy}>
                    {ROLE_LABEL[role]}
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
              {onSuggestNumbers && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={onSuggestNumbers}>Suggest numbers…</DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      {checklist && <ReaderChecklist questions={checklist} />}
    </li>
  )
}

/** "What to look for": a closed-by-default disclosure listing the role's reader questions. Sibling of the jump button. */
function ReaderChecklist({ questions }: { questions: readonly string[] }) {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="ml-2 flex flex-col gap-1 text-xs">
      <Collapsible.Trigger asChild>
        <Button variant="ghost" size="xs" className="self-start text-muted-foreground">
          What to look for
          <ChevronDown aria-hidden className={cn('transition-transform', open && 'rotate-180')} />
        </Button>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          {questions.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
