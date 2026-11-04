import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { keys, PAPERS_POLL_MS } from '@/api/queries'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'

/** How far a paper's embedding has got. Mount it only while the paper is embedding: it polls for as long as it's up. */
export function EmbeddingProgress({ paperId, className }: { paperId: string; className?: string }) {
  const { data } = useQuery({
    queryKey: keys.embeddingProgress(paperId),
    queryFn: () => api.embeddingProgress(paperId),
    refetchInterval: PAPERS_POLL_MS,
  })
  if (!data?.total) return null
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <p className="text-xs tabular-nums text-muted-foreground">
        Preparing search: {data.done.toLocaleString()} of {data.total.toLocaleString()} passages
      </p>
      <Progress aria-label="Preparing search" value={Math.round((100 * data.done) / data.total)} />
    </div>
  )
}
