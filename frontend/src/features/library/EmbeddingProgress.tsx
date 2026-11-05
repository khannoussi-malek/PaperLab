import { useQuery } from '@tanstack/react-query'
import { useRef } from 'react'
import { api } from '@/api/client'
import { keys, PAPERS_POLL_MS } from '@/api/queries'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

const MIN_SECONDS = 20 // a shorter sample says little: the first slice starts with the model still loading

/** The time left at the speed since this page started watching, in words; null until that speed means something. */
export function timeLeft(done: number, total: number, startDone: number, seconds: number): string | null {
  if (seconds < MIN_SECONDS || done <= startDone) return null
  const minutes = ((total - done) * seconds) / (done - startDone) / 60
  if (minutes < 1) return 'less than a minute left'
  if (minutes < 90) return `about ${Math.round(minutes)} minutes left`
  return `about ${Math.round(minutes / 60)} hours left`
}

/** How far a paper's embedding has got. Mount it only while the paper is embedding: it polls for as long as it's up. */
export function EmbeddingProgress({ paperId, className }: { paperId: string; className?: string }) {
  const { data, dataUpdatedAt } = useQuery({
    queryKey: keys.embeddingProgress(paperId),
    queryFn: () => api.embeddingProgress(paperId),
    refetchInterval: PAPERS_POLL_MS,
  })
  const start = useRef<{ done: number; at: number } | null>(null)
  if (!data?.total) return null
  start.current ??= { done: data.done, at: dataUpdatedAt }
  const left = timeLeft(data.done, data.total, start.current.done, (dataUpdatedAt - start.current.at) / 1000)
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <p className="text-xs tabular-nums text-muted-foreground">
        Preparing search: {data.done.toLocaleString()} of {data.total.toLocaleString()} passages
        {left && `, ${left}`}
      </p>
      <Progress aria-label="Preparing search" value={Math.round((100 * data.done) / data.total)} />
    </div>
  )
}
