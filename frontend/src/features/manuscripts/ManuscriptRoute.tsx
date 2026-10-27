import { lazy, Suspense, useMemo, useState } from 'react'
import { RouteErrorBoundary } from '@/components/RouteErrorBoundary'

// The editor brings CodeMirror, so it loads only when a manuscript opens.
const load = () => import('./ManuscriptPage').then((m) => ({ default: m.ManuscriptPage }))

/** The lazy editor route. Try again builds a fresh lazy component, because React keeps a failed one failed. */
export function ManuscriptRoute({ manuscriptId, file, line = null }: { manuscriptId: string; file: string | null; line?: number | null }) {
  const [attempt, setAttempt] = useState(0)
  const Page = useMemo(() => lazy(load), [attempt])
  return (
    <RouteErrorBoundary key={attempt} onRetry={() => setAttempt((a) => a + 1)}>
      <Suspense fallback={<p role="status" className="p-4 text-sm text-muted-foreground">Loading the editor…</p>}>
        <Page manuscriptId={manuscriptId} file={file} line={line} />
      </Suspense>
    </RouteErrorBoundary>
  )
}
