import { lazy, Suspense, useState, type ComponentType } from 'react'
import { AppShell } from '@/components/AppShell'
import { RouteErrorBoundary } from '@/components/RouteErrorBoundary'

/**
 * A page whose code loads the first time it opens, so the first window doesn't wait for every page's code.
 * While it loads, the shell (and the sidebar, which moves into it) stays on screen. A chunk that fails to arrive shows
 * Try again, which builds a fresh lazy component: React keeps a failed one failed.
 */
// ponytail: `bare` for the views that take the whole window (reader, setup) so their loading text has no shell around it.
export function lazyPage<P extends object>(load: () => Promise<ComponentType<P>>, { bare = false } = {}) {
  const fresh = () => lazy(() => load().then((Page) => ({ default: Page })))
  // One lazy component for every mount, so reopening a loaded page renders at once instead of suspending again.
  let Loaded = fresh()
  function LazyPage(props: P) {
    const [attempt, setAttempt] = useState(0)
    const retry = () => {
      Loaded = fresh()
      setAttempt((a) => a + 1)
    }
    const loading = <p role="status" className="p-4 text-sm text-muted-foreground">Loading…</p>
    return (
      <RouteErrorBoundary key={attempt} onRetry={retry}>
        <Suspense fallback={bare ? loading : <AppShell title={null}>{loading}</AppShell>}>
          <Loaded {...props} />
        </Suspense>
      </RouteErrorBoundary>
    )
  }
  return LazyPage
}
