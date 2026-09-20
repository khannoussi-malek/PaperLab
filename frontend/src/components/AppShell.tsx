import { ArrowLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { glass } from '@/components/glass'
import { ModeToggle } from '@/components/mode-toggle'
import { fadeIn } from '@/components/motion'
import { NavRail } from '@/components/NavRail'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** The shell's own `h1`. Exported so a view that draws its own (an editable title) matches the rest. */
export const shellTitle = 'min-w-0 truncate font-heading text-base leading-none font-semibold'

type Props = {
  /** A string becomes the toolbar's `h1`; a node is drawn as-is and must contain its own `h1` (see `shellTitle`). */
  title: ReactNode
  /** A drill-down's way back up, as a leading toolbar button: a chart to Charts, a dataset to where it came from. */
  back?: { href: string; label: string }
  /** This view's actions, at the right of the toolbar, before the theme toggle. */
  actions?: ReactNode
  /** This view's line in the status bar: counts, and what the view is showing. */
  status?: ReactNode
  /**
   * `true` when the view lays itself out to the pane's height (the graph, the workspace tabs) and scrolls its own
   * regions; `false` (the default) when the pane scrolls the view.
   */
  fills?: boolean
  children: ReactNode
}

/**
 * PaperLab's window: a toolbar across the top, the navigation rail down the left, the view in the middle and a status
 * bar along the bottom (see "Shell" in design-system/MASTER.md). It is the same chrome on every view, so only the
 * middle changes as you move around; nothing here scrolls but the rail and the view.
 *
 * The reader and first-run setup do not use it: both take the whole window on purpose.
 *
 * ponytail: each view renders its own `AppShell`, so React remounts the chrome on every navigation. It looks
 * seamless (the workspaces come from React Query's cache, and nothing shifts), but the rail's scroll position
 * resets. Lift the shell into `App` and have views publish title/actions/status through a context if the rail ever
 * grows long enough to scroll.
 */
export function AppShell({ title, back, actions, status, fills = false, children }: Props) {
  return (
    <div className="grid h-dvh grid-cols-[14rem_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden">
      <header className={cn('col-span-full flex h-11 items-center gap-1 border-b border-glass-border px-2', glass)}>
        {back && (
          <Button variant="ghost" size="sm" asChild className="shrink-0 text-muted-foreground">
            <a href={back.href}>
              <ArrowLeft aria-hidden />
              {back.label}
            </a>
          </Button>
        )}
        <div className="flex min-w-0 flex-1 items-center px-1.5">
          {typeof title === 'string' ? (
            <h1 className={shellTitle} title={title}>
              {title}
            </h1>
          ) : (
            title
          )}
        </div>
        {actions}
        <ModeToggle />
      </header>

      <NavRail />

      {/* Keyed by nothing: the view inside changes with the route, and fades in as it arrives. */}
      <main className={cn('min-w-0', fills ? 'flex min-h-0 flex-col overflow-hidden p-3' : 'overflow-auto p-3', fadeIn)}>
        {children}
      </main>

      {/* `.status-bar` is the stable hook for this view's counts, wherever the specs used to read them off a header. */}
      <footer className="status-bar col-span-full flex h-6 items-center gap-2 border-t border-glass-border px-3 text-xs text-muted-foreground">
        {status}
      </footer>
    </div>
  )
}
