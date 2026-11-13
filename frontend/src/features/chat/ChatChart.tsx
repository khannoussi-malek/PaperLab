import { useChartMutations } from '@/api/queries'
import type { ChartSpec } from '@/api/client'
import { Button } from '@/components/ui/button'
import { ChartView } from '@/features/charts/ChartView'
import { chartHref } from '@/lib/route'

/** A chart answer's chart (M14): drawn from the captured cells the spec names, never from numbers in the answer. */
export function ChatChart({ spec, title }: { spec: ChartSpec; title: string }) {
  const { create } = useChartMutations()
  return (
    <div className="grid gap-2">
      <ChartView spec={spec} height={300} />
      <div className="flex items-center gap-2 text-sm">
        {create.data ? (
          <a className="text-primary underline-offset-4 hover:underline" href={chartHref(create.data.id)}>
            Open saved chart
          </a>
        ) : (
          <Button type="button" size="sm" variant="outline" disabled={create.isPending} onClick={() => create.mutate({ title, spec })}>
            Save chart
          </Button>
        )}
        {create.error && <span role="alert" className="text-destructive">{create.error.message}</span>}
      </div>
    </div>
  )
}
