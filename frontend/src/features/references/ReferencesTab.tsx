import { RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReferencesDirection } from '@/api/client'
import { useReferences, useRefreshReferences } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ErrorAlert, LoadError } from '@/features/library/ErrorAlert'
import { ReferenceRow } from './ReferenceRow'
import { summaryLine } from './referencesMeta'

const SKELETON_ROWS = 3

/** The reader's References tab. Asks Semantic Scholar (and OpenAlex, when on) only once the tab has been opened,
 * which also queues the first fetch (D78): a paper that has never been fetched goes straight to "fetching". */
export function ReferencesTab({ paperId, active, workspaceId }: { paperId: string; active: boolean; workspaceId?: string }) {
  const [direction, setDirection] = useState<ReferencesDirection>('cites')
  const references = useReferences(paperId, direction, active)
  const refresh = useRefreshReferences(paperId)
  const data = references.data

  // Fires once per mount (RightPanel keeps every tab mounted, so this component's lifetime is the whole reader
  // visit): a ref survives StrictMode's double-invoked effect, unlike a variable reset on every render.
  const firedRef = useRef(false)
  useEffect(() => {
    if (active && data?.state === 'none' && !firedRef.current) {
      firedRef.current = true
      refresh.mutate()
    }
  }, [active, data?.state, refresh])

  const summary = data?.state === 'ready' ? summaryLine(data.summary, data.direction) : null

  return (
    // RightPanel draws the glass and the border, as for Notes, Data and Similar.
    <aside className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4" aria-label="References">
      <p className="text-sm text-muted-foreground">
        What this paper cites, and what has cited it since — ranked for your library.
      </p>
      <Tabs value={direction} onValueChange={(value) => setDirection(value as ReferencesDirection)}>
        <TabsList>
          <TabsTrigger value="cites">Cited</TabsTrigger>
          <TabsTrigger value="cited_by">Citing</TabsTrigger>
        </TabsList>
      </Tabs>

      {references.isError && <LoadError message={references.error.message} onRetry={() => void references.refetch()} />}

      {!data && !references.isError && <p className="text-muted-foreground">Loading references…</p>}

      {(data?.state === 'none' || data?.state === 'fetching') &&
        (refresh.error ? (
          // The request that queues the fetch failed, so nothing is fetching: say why instead of waiting forever.
          <>
            <ErrorAlert message={refresh.error.message} />
            <Button variant="outline" className="self-start" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
              Try again
            </Button>
          </>
        ) : (
          <>
            <p role="status" className="text-muted-foreground">
              Fetching references…
            </p>
            <div aria-hidden className="flex flex-col gap-2">
              {Array.from({ length: SKELETON_ROWS }, (_, i) => (
                <div key={i} className="h-16 animate-pulse rounded-xl bg-muted" />
              ))}
            </div>
          </>
        ))}

      {data?.state === 'failed' && (
        <>
          <ErrorAlert message={data.error ?? 'References could not be fetched.'} />
          <Button variant="outline" className="self-start" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            Try again
          </Button>
          {refresh.error && <ErrorAlert message={refresh.error.message} />}
        </>
      )}

      {data?.state === 'ready' && (
        <>
          <div className="flex items-center gap-2">
            {summary && <p className="references-summary text-sm text-muted-foreground">{summary}</p>}
            <Button size="sm" variant="ghost" className="ml-auto" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
              <RefreshCw aria-hidden />
              Refresh
            </Button>
          </div>
          {refresh.error && <ErrorAlert message={refresh.error.message} />}
          {data.rows.length === 0 ? (
            <p className="text-muted-foreground">This paper's sources list no references.</p>
          ) : (
            <ul className="reference-list divide-y divide-glass-border rounded-xl border border-glass-border">
              {data.rows.map((row) => (
                <ReferenceRow
                  key={row.id}
                  paperId={paperId}
                  reference={row}
                  direction={data.direction}
                  workspaceId={workspaceId}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </aside>
  )
}
