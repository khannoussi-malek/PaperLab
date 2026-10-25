import { Ellipsis } from 'lucide-react'
import type { Role, Section } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ROLE_LABEL } from './lenses'

const AUTOMATIC = 'automatic'
const ROLES = Object.keys(ROLE_LABEL) as Role[]

type Props = {
  section: Section
  /** A role fix is being saved: the menu waits. */
  busy: boolean
  onJump: () => void
  /** null: back to the automatic role. Only offered on a section with a heading. */
  onRoleChange: (role: Role | null) => void
}

/** One section in the Lens tab: its heading, role and page, a click to jump there, and ⋯ to change its role. */
export function SectionRow({ section, busy, onJump, onRoleChange }: Props) {
  const title = section.title ?? 'Before the first heading'
  const fixed = section.source === 'user'
  return (
    <li className="lens-section flex items-start gap-1" data-role={section.role}>
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
          {fixed && <span className="role-fixed">you</span>}
          <span className="tabular-nums">p. {section.page}</span>
        </span>
        <span className="line-clamp-2 text-xs text-muted-foreground" title={section.preview}>
          {section.preview}
        </span>
      </button>
      {section.title !== null && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Section actions for ${section.title}`} disabled={busy}>
              <Ellipsis aria-hidden />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Change role</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={fixed ? section.role : AUTOMATIC}
              onValueChange={(value) => onRoleChange(value === AUTOMATIC ? null : (value as Role))}
            >
              <DropdownMenuRadioItem value={AUTOMATIC}>Automatic</DropdownMenuRadioItem>
              <DropdownMenuSeparator />
              {ROLES.map((role) => (
                <DropdownMenuRadioItem key={role} value={role}>
                  {ROLE_LABEL[role]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </li>
  )
}
