import type { ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { workspaceHref } from '@/lib/route'
import { WORKSPACE_TABS } from './workspaceTabs'

/** Placeholder bars while a tab's data loads, so a loading tab never reads as an empty one. */
export function TabSkeleton({ rows = 3, label }: { rows?: number; label: string }) {
  return (
    <div role="status" aria-busy="true" className="flex flex-col gap-2 py-2">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} data-skeleton-row className="h-10 animate-pulse rounded-lg bg-muted motion-reduce:animate-none" />
      ))}
    </div>
  )
}

/** What an empty tab shows: a title, one sentence and the next step. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-xl border border-dashed border-glass-border px-6 py-10">
      <h2 className="text-base font-medium">{title}</h2>
      {children && <p className="max-w-prose text-sm text-muted-foreground">{children}</p>}
      {action}
    </div>
  )
}

const SEARCH_TAB = WORKSPACE_TABS.find((t) => t.value === 'search')!

/** "Go to 1 · Search & screen", a plain link styled as a button. */
export function GoToSearchAction({ workspaceId, runId }: { workspaceId: string; runId?: string | null }) {
  return (
    <Button asChild variant="outline" size="sm">
      <a href={workspaceHref(workspaceId, 'search', runId)}>{`Go to ${SEARCH_TAB.step} · ${SEARCH_TAB.label}`}</a>
    </Button>
  )
}
