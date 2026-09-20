import type { Route } from '@/lib/route'
import { cn } from '@/lib/utils'

/**
 * Which rail item a route lights up. Drill-downs light up the section they were reached from (a chart and a dataset
 * belong to Charts), so the rail never goes blank while you are deep inside one. `null` is for the two views that take
 * the whole window and draw no rail: the reader and first-run setup.
 */
export type NavKey = 'library' | 'workspace' | 'graph' | 'charts' | 'connect-claude' | 'settings' | null

export function activeNav(route: Route): NavKey {
  switch (route.name) {
    case 'library':
      return 'library'
    case 'workspace':
      return 'workspace'
    case 'graph':
      return 'graph'
    case 'charts':
    case 'chart':
    case 'chart-builder':
    case 'dataset':
      return 'charts'
    case 'connect-claude':
      return 'connect-claude'
    case 'settings':
      return 'settings'
    default:
      return null
  }
}

/** The workspace the rail marks as current, or null when the route isn't inside one. */
export const activeWorkspaceId = (route: Route): string | null => (route.name === 'workspace' ? route.workspaceId : null)

/**
 * One row in the navigation rail. Desktop density: 28 px tall, 13 px text, the whole row is the target. The current
 * row carries a left bar as well as a tint, so it reads as current without relying on colour.
 */
export const railItem = (active: boolean) =>
  cn(
    'flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none transition-colors duration-150 hover:bg-foreground/5 focus-visible:ring-3 focus-visible:ring-ring/50',
    active && 'bg-primary/10 font-medium shadow-[inset_3px_0_0_var(--color-primary)]',
  )
