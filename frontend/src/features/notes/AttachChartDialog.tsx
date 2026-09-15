import type { Note } from '@/api/client'
import { useChartMutations, useCharts } from '@/api/queries'
import { glass } from '@/components/glass'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { chartsHref } from '@/lib/route'
import { cn } from '@/lib/utils'

type Props = {
  note: Note
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** A searchable list of saved charts not already attached to this note. Follows `AddPapersDialog`. */
export function AttachChartDialog({ note, open, onOpenChange }: Props) {
  const charts = useCharts()
  const { attach } = useChartMutations()
  const attachedIds = new Set((note.charts ?? []).map((chart) => chart.id))
  const candidates = (charts.data ?? []).filter((chart) => !attachedIds.has(chart.id))

  function close() {
    attach.reset()
    onOpenChange(false)
  }

  function pick(chartId: string) {
    attach.mutate({ noteId: note.id, chartId }, { onSuccess: close })
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className={cn(glass, 'bg-glass-strong ring-glass-border sm:max-w-lg')}>
        <DialogHeader>
          <DialogTitle>Attach chart</DialogTitle>
          <DialogDescription>Show a saved chart inside this note.</DialogDescription>
        </DialogHeader>
        <Command className="bg-transparent p-0">
          <CommandInput aria-label="Search charts" placeholder="Search your charts…" />
          <CommandList>
            <CommandEmpty>
              {charts.isPending ? (
                'Loading your charts…'
              ) : charts.isError ? (
                "Couldn't load your charts."
              ) : (charts.data?.length ?? 0) === 0 ? (
                <>
                  No charts yet.{' '}
                  <a href={chartsHref} className="text-primary hover:underline">
                    Build one on the Charts page.
                  </a>
                </>
              ) : candidates.length === 0 ? (
                'Every chart is already attached to this note.'
              ) : (
                'No matching charts.'
              )}
            </CommandEmpty>
            {!charts.isPending &&
              !charts.isError &&
              candidates.map((chart) => (
                <CommandItem
                  key={chart.id}
                  value={chart.id}
                  keywords={[chart.title, ...chart.sources]}
                  data-chart-id={chart.id}
                  onSelect={() => pick(chart.id)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate" title={chart.title}>
                      {chart.title}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">{chart.sources.join(', ')}</p>
                  </div>
                </CommandItem>
              ))}
          </CommandList>
        </Command>
        {charts.isError && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{charts.error.message}</AlertDescription>
          </Alert>
        )}
        {attach.error && (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>{attach.error.message}</AlertDescription>
          </Alert>
        )}
      </DialogContent>
    </Dialog>
  )
}
