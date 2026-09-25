import { PencilLine } from 'lucide-react'
import { useState } from 'react'
import type { Note } from '@/api/client'
import { useChart, useChartMutations } from '@/api/queries'
import { AppShell, shellTitle } from '@/components/AppShell'
import { glass } from '@/components/glass'
import { delayedIn } from '@/components/motion'
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
    <AppShell
      back={{ href: chartsHref, label: 'Charts' }}
      title={
        chart.data ? (
          <InlineTitle as="h1" value={chart.data.title} label="Chart title" editing={renaming} onEditingChange={setRenaming} onSave={saveTitle} />
        ) : (
          <h1 className={cn(shellTitle, !chart.isError && delayedIn)} title={title}>
            {title}
          </h1>
        )
      }
      actions={
        chart.data && (
          <>
            <Button variant="ghost" size="sm" asChild>
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
        )
      }
      status={chart.data && `Used in ${plural(chart.data.note_ids.length, 'note')}`}
    >
      <div className="flex max-w-5xl flex-col gap-4">
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
            Added to a note in {plural(noteResult.note.paper_ids.length, 'paper')}.
            <a href={noteHref(noteResult.note.paper_ids[0], noteResult.note.id)} className="text-primary hover:underline">
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
      </div>
    </AppShell>
  )
}
