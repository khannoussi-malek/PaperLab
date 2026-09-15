import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ChartRef, Note } from '@/api/client'
import { useChart, useChartMutations } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { chartHref } from '@/lib/route'
import { ChartView } from '../charts/ChartView'

const HEIGHT = 160

/** One attached chart: its title, its plot once the card is near the viewport, and a way to remove it. */
function NoteChartEmbed({ noteId, chartRef }: { noteId: string; chartRef: ChartRef }) {
  const [el, setEl] = useState<HTMLDivElement | null>(null)
  const [nearViewport, setNearViewport] = useState(false)
  // Fetched only once near the viewport: an off-screen chart shouldn't cost a request.
  const chart = useChart(nearViewport ? chartRef.id : null)
  const { detach } = useChartMutations()

  useEffect(() => {
    if (!el || nearViewport) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return
        setNearViewport(true)
        observer.disconnect()
      },
      { rootMargin: '200px' },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [el, nearViewport])

  return (
    <div ref={setEl} className="note-chart flex flex-col gap-1" data-chart-id={chartRef.id}>
      <div className="flex items-center justify-between gap-1">
        <a href={chartHref(chartRef.id)} title={chartRef.title} className="min-w-0 truncate text-sm font-medium hover:underline">
          {chartRef.title}
        </a>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Remove chart"
          title="Remove chart"
          className="shrink-0 text-muted-foreground"
          onClick={() => detach.mutate({ noteId, chartId: chartRef.id })}
        >
          <X aria-hidden />
        </Button>
      </div>
      {nearViewport && chart.data ? (
        <ChartView spec={chart.data.spec} height={HEIGHT} staticPlot withTable={false} />
      ) : (
        // Reserves the plot's height so it doesn't appear once drawn.
        <div style={{ height: HEIGHT }} />
      )}
    </div>
  )
}

/** The charts attached to a note: each drawn once scrolled near the viewport. Renders nothing without any. */
export function NoteCharts({ note }: { note: Note }) {
  // Defensive: a note not fresh from the real API (a test double, an older cache entry) may omit `charts`.
  const charts = note.charts ?? []
  if (charts.length === 0) return null
  return (
    <div className="flex flex-col gap-3">
      {charts.map((chartRef) => (
        <NoteChartEmbed key={chartRef.id} noteId={note.id} chartRef={chartRef} />
      ))}
    </div>
  )
}
