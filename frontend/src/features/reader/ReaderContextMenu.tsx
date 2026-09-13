import { Copy, NotebookPen, Pencil, Trash2, X } from 'lucide-react'
import type { Note } from '@/api/client'
import { glass } from '@/components/glass'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { PRESET_COLORS } from '../notes/highlightColors'

export type ContextTarget = { kind: 'note'; note: Note; quote: string } | { kind: 'draft'; quote: string }

export type ContextMenuState = { x: number; y: number; target: ContextTarget }

type Props = {
  menu: ContextMenuState | null
  onClose: () => void
  onColorNote: (note: Note, hex: string) => void
  onEditNote: (note: Note) => void
  onDeleteNote: (note: Note) => void
  onHighlightDraft: (hex: string) => void
  onAddNote: () => void
  onCancelDraft: () => void
}

const Swatch = ({ hex }: { hex: string }) => (
  <span aria-hidden className="size-3 rounded-full ring-1 ring-foreground/20" style={{ backgroundColor: hex }} />
)

const copy = (text: string) => void navigator.clipboard?.writeText(text)

/** Right-click menu for a highlight or the pending selection, opened where the user clicked. */
export function ReaderContextMenu({ menu, onClose, ...actions }: Props) {
  const target = menu?.target
  return (
    <DropdownMenu open={menu !== null} onOpenChange={(open) => !open && onClose()}>
      {/* A zero-size trigger at the pointer, so the menu opens at the click point. */}
      <DropdownMenuTrigger asChild>
        <span aria-hidden className="pointer-events-none fixed size-0" style={{ left: menu?.x ?? 0, top: menu?.y ?? 0 }} />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className={cn(glass, 'bg-glass-strong ring-glass-border')}
        // Don't hand focus back to the invisible trigger; actions like "Add note…" move focus themselves.
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        {target?.kind === 'note' && (
          <>
            {PRESET_COLORS.map((color) => (
              <DropdownMenuItem key={color.hex} onSelect={() => actions.onColorNote(target.note, color.hex)}>
                <Swatch hex={color.hex} />
                {color.name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => actions.onEditNote(target.note)}>
              <Pencil aria-hidden />
              Edit note
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => copy(target.quote)}>
              <Copy aria-hidden />
              Copy quote
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={() => actions.onDeleteNote(target.note)}>
              <Trash2 aria-hidden />
              Delete note
            </DropdownMenuItem>
          </>
        )}
        {target?.kind === 'draft' && (
          <>
            {PRESET_COLORS.map((color) => (
              <DropdownMenuItem key={color.hex} onSelect={() => actions.onHighlightDraft(color.hex)}>
                <Swatch hex={color.hex} />
                Highlight in {color.name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={actions.onAddNote}>
              <NotebookPen aria-hidden />
              Add note…
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => copy(target.quote)}>
              <Copy aria-hidden />
              Copy text
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={actions.onCancelDraft}>
              <X aria-hidden />
              Cancel
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
