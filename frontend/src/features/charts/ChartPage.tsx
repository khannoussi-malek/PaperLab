import { PencilLine } from 'lucide-react'
import { useState } from 'react'
import type { Note } from '@/api/client'
import { useChart, useChartMutations } from '@/api/queries'
import { glass } from '@/components/glass'
import { fadeIn } from '@/components/motion'
import { ModeToggle } from '@/components/mode-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { chartsHref, editChartHref, noteHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { ChartMenu } from './ChartMenu'
import { ChartView } from './ChartView'
import { InlineTitle } from './InlineTitle'

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

/** A saved chart's own page: its renameable title, its actions menu, and its live drawing. */
export function ChartPage({ chartId }: { chartId: string }) {
  const chart = useChart(chartId)
  const { update } = useChartMutations()
  const [renaming, setRenaming] = useState(false)
  const [noteResult, setNoteResult] = useState<{ note: Note } | { error: string } | null>(null)
  const title = chart.data?.title ?? (chart.isError ? 'Chart not found' : 'Loading…')

  async function saveTitle(next: string) {
    await update.mutateAsync({ id: chartId, title: next })
    return true
  }

  return (
    <main className={cn('mx-auto flex max-w-5xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" asChild className="-ml-2.5">
            <a href={chartsHref}>← Charts</a>
          </Button>
          {chart.data ? (
            <InlineTitle as="h1" value={chart.data.title} label="Chart title" editing={renaming} onEditingChange={setRenaming} onSave={saveTitle} />
          ) : (
            <h1 className="mt-1 truncate font-heading text-3xl font-semibold" title={title}>
              {title}
            </h1>
          )}
        </div>
        <div className="flex items-center gap-2">
          {chart.data && (
            <>
              <Button variant="outline" asChild>
                <a href={editChartHref(chart.data.id)}>
                  <PencilLine aria-hidden />
                  Edit
                </a>
              </Button>
              <ChartMenu
                chart={{ id: chart.data.id, title: chart.data.title, note_count: chart.data.note_ids.length }}
                onRename={() => setRenaming(true)}
                withEdit={false}
                onAddToNote={setNoteResult}
                onError={(error) => setNoteResult({ error })}
              />
            </>
          )}
          <ModeToggle />
        </div>
      </header>

      {chart.isError && !chart.data && (
        <p className="text-muted-foreground">
          This chart doesn't exist.{' '}
          <a href={chartsHref} className="text-primary hover:underline">
            Back to Charts
          </a>
          .
        </p>
      )}

      {noteResult &&
        ('note' in noteResult ? (
          <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
            Added to a note in {plural(new Set(noteResult.note.anchors.map((a) => a.paper_id)).size, 'paper')}.
            <a href={noteHref(noteResult.note.anchors[0].paper_id, noteResult.note.id)} className="text-primary hover:underline">
              Open the note
            </a>
          </p>
        ) : (
          <Alert variant="destructive" className="border-glass-border">
            <AlertDescription>
              {noteResult.error === 'chart_has_no_paper_data'
                ? "This chart only uses your own data, so there's no paper to note it in. Attach it to a note instead."
                : noteResult.error}
            </AlertDescription>
          </Alert>
        ))}

      {chart.data && (
        <Card className={cn('ring-glass-border', glass)}>
          <CardContent>
            <ChartView spec={chart.data.spec} />
          </CardContent>
        </Card>
      )}
    </main>
  )
}
