import type { ChartUse } from '@/api/client'
import { glass } from '@/components/glass'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { chartHref } from '@/lib/route'
import { cn } from '@/lib/utils'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The charts that name a column the draft no longer has (`chartsLosingColumns`). */
  charts: ChartUse[]
  pending: boolean
  onConfirm: () => void
}

/** Asked before a grid save drops a column charts use: named charts, Cancel or save anyway. */
export function ChartsUsingDataDialog({ open, onOpenChange, charts, pending, onConfirm }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-md')}>
        <DialogHeader>
          <DialogTitle>Charts use this data</DialogTitle>
          <DialogDescription>These charts use a column this save removes. They'll lose that data.</DialogDescription>
        </DialogHeader>
        <ul className="flex flex-col gap-1">
          {charts.map((chart) => (
            <li key={chart.id}>
              <a href={chartHref(chart.id)} className="text-sm text-primary hover:underline">
                {chart.title}
              </a>
            </li>
          ))}
        </ul>
        <DialogFooter className="bg-transparent">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" disabled={pending} onClick={onConfirm}>
            Save anyway
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
