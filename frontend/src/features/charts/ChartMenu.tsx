import { Copy, EllipsisVertical, NotebookPen, Pencil, SquarePen, Trash2 } from 'lucide-react'
import { useRef } from 'react'
import type { Note } from '@/api/client'
import { useChartMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { chartHref, chartsHref, editChartHref, useRoute } from '@/lib/route'
import { cn } from '@/lib/utils'

type Props = {
  chart: { id: string; title: string; note_count: number }
  /** Starts the inline rename; the caller owns that state (the list keeps one row's, the chart page its own). */
  onRename: () => void
  /** The list keeps "Edit" in this menu; the chart page shows its own outline "Edit" button instead. */
  withEdit?: boolean
  /** The chart page's own "Add to note…" item; the list rows don't offer it. Told the outcome to show. */
  onAddToNote?: (result: { note: Note } | { error: string }) => void
}

const menuSurface = cn(glass, 'bg-glass-strong ring-glass-border')

const noteCount = (count: number) => `${count} note${count === 1 ? '' : 's'}`

/**
 * A chart's "Chart actions" menu, shared by the Charts list and the chart page. Duplicate and Delete navigate to the
 * result only when this chart's own page is open; on the list they leave it as is.
 */
export function ChartMenu({ chart, onRename, withEdit = true, onAddToNote }: Props) {
  const route = useRoute()
  const onOwnPage = route.name === 'chart' && route.chartId === chart.id
  const { duplicate, remove, addToNote } = useChartMutations()

  // Renaming replaces this row's title with an autofocused input. Starting it only once this menu has actually
  // finished closing — rather than immediately on select — means that autofocus never has to fight Radix's own
  // focus trap, which stays mounted (and active) through the ~100ms exit animation and would otherwise win the
  // race, pulling focus back out to the (still-mounted) "Chart actions" trigger mid-edit. Same underlying fix as
  // `WorkspaceSidebar`'s `suppressMenuAutoFocusRef`, timed to this menu's own close instead.
  const pendingRenameRef = useRef(false)

  function startRename() {
    pendingRenameRef.current = true
  }

  function duplicateChart() {
    duplicate.mutate(chart.id, {
      onSuccess: (created) => {
        if (onOwnPage) window.location.hash = chartHref(created.id)
      },
    })
  }

  async function addChartToNote() {
    try {
      const note = await addToNote.mutateAsync(chart.id)
      onAddToNote?.({ note })
    } catch (e) {
      onAddToNote?.({ error: e instanceof Error ? e.message : "Couldn't add to a note." })
    }
  }

  function deleteChart() {
    const question = chart.note_count
      ? `Delete "${chart.title}"? It's shown in ${noteCount(chart.note_count)}; the notes are kept.`
      : `Delete "${chart.title}"?`
    if (!window.confirm(question)) return
    remove.mutate(chart.id, {
      onSuccess: () => {
        if (onOwnPage) window.location.hash = chartsHref
      },
    })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label="Chart actions" title="Chart actions" className="text-muted-foreground">
          <EllipsisVertical aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className={menuSurface}
        // Fires once this menu has actually finished closing (its focus trap released). Rename starts here, not
        // in its own `onSelect`, and this prevents Radix's default of handing focus back to the trigger; every
        // other close (Escape, Edit's own navigation, Duplicate, Delete's confirm-then-mutate) takes that default.
        onCloseAutoFocus={(event) => {
          if (!pendingRenameRef.current) return
          event.preventDefault()
          pendingRenameRef.current = false
          onRename()
        }}
      >
        {withEdit && (
          <DropdownMenuItem asChild>
            <a href={editChartHref(chart.id)}>
              <SquarePen aria-hidden />
              Edit
            </a>
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={startRename}>
          <Pencil aria-hidden />
          Rename
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={duplicateChart}>
          <Copy aria-hidden />
          Duplicate
        </DropdownMenuItem>
        {onAddToNote && (
          <DropdownMenuItem onSelect={() => void addChartToNote()}>
            <NotebookPen aria-hidden />
            Add to note…
          </DropdownMenuItem>
        )}
        <DropdownMenuItem variant="destructive" onSelect={deleteChart}>
          <Trash2 aria-hidden />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
