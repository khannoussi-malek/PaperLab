import { Copy, EllipsisVertical, Pencil, SquarePen, Trash2 } from 'lucide-react'
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
}

const menuSurface = cn(glass, 'bg-glass-strong ring-glass-border')

/**
 * A chart's "Chart actions" menu, shared by the Charts list and the chart page. Duplicate and Delete navigate to the
 * result only when this chart's own page is open; on the list they leave it as is.
 */
export function ChartMenu({ chart, onRename }: Props) {
  const route = useRoute()
  const onOwnPage = route.name === 'chart' && route.chartId === chart.id
  const { duplicate, remove } = useChartMutations()

  function duplicateChart() {
    duplicate.mutate(chart.id, {
      onSuccess: (created) => {
        if (onOwnPage) window.location.hash = chartHref(created.id)
      },
    })
  }

  function deleteChart() {
    const question = chart.note_count
      ? `Delete "${chart.title}"? It's shown in ${chart.note_count} note(s); the notes are kept.`
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
      <DropdownMenuContent align="end" className={menuSurface}>
        <DropdownMenuItem asChild>
          <a href={editChartHref(chart.id)}>
            <SquarePen aria-hidden />
            Edit
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onRename}>
          <Pencil aria-hidden />
          Rename
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={duplicateChart}>
          <Copy aria-hidden />
          Duplicate
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onSelect={deleteChart}>
          <Trash2 aria-hidden />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
