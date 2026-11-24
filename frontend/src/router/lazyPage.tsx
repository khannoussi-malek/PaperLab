import { lazy, Suspense, useState, type ComponentType } from 'react'
import { AppShell } from '@/layout/AppShell'
import { delayedIn } from '@/components/motion'
import { RouteErrorBoundary } from '@/components/RouteErrorBoundary'
import { cn } from '@/lib/utils'

/**
 * A page whose code loads the first time it opens, so the first window doesn't wait for every page's code.
 * While it loads, the shell (and the sidebar, which moves into it) stays on screen. `preload()` fetches the code
 * ahead, so a navigation can fade straight to the page. A chunk that fails to arrive shows Try again, which loads it
 * afresh.
 */
// ponytail: `bare` for the views that take the whole window (reader, setup) so their loading text has no shell around it.
export function lazyPage<P extends object>(load: () => Promise<ComponentType<P>>, { bare = false } = {}) {
  let Loaded: ComponentType<P> | null = null
  let pending: Promise<void> | null = null
  const preload = () =>
    (pending ??= load().then(
      (Page) => {
        Loaded = Page
      },
      (error: unknown) => {
        pending = null // the next try fetches again
        throw error
      },
    ))

  // React keeps a failed lazy component failed, so Try again builds a fresh one.
  const fresh = () => lazy(() => preload().then(() => ({ default: Loaded as ComponentType<P> })))
  let Lazy = fresh()

  function Page(props: P) {
    // Code already here renders at once; otherwise the lazy one suspends. A mount keeps the one it started with, so a
    // load finishing never swaps the component (and remounts the page) under it.
    const [Component] = useState(() => Loaded ?? Lazy)
    return <Component {...props} />
  }

  function LazyPage(props: P) {
    const [attempt, setAttempt] = useState(0)
    const loading = (
      <p role="status" className={cn('p-4 text-sm text-muted-foreground', delayedIn)}>
        Loading…
      </p>
    )
    return (
      <RouteErrorBoundary
        key={attempt}
        onRetry={() => {
          Lazy = fresh()
          setAttempt((a) => a + 1)
        }}
      >
        <Suspense fallback={bare ? loading : <AppShell title={null}>{loading}</AppShell>}>
          <Page {...props} />
        </Suspense>
      </RouteErrorBoundary>
    )
  }
  return Object.assign(LazyPage, { preload })
}
