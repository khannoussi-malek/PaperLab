import { BookMarked, ChartColumn, Library, Plug, Settings, Share2, StickyNote, type LucideIcon } from 'lucide-react'
import { glass } from '@/components/glass'
import { activeNav, activeWorkspaceId, railItem, type NavKey } from '@/components/nav'
import { useRailPill } from '@/components/useRailPill'
import { WorkspaceSidebar } from '@/features/workspaces/WorkspaceSidebar'
import { chartsHref, connectClaudeHref, graphHref, notesHref, referencesHref, settingsHref, useRoute } from '@/lib/route'
import { cn } from '@/lib/utils'

function RailLink({ href, icon: Icon, label, active }: { href: string; icon: LucideIcon; label: string; active: boolean }) {
  return (
    <a href={href} aria-current={active ? 'page' : undefined} className={railItem(active, true)}>
      <Icon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      <span className="truncate">{label}</span>
    </a>
  )
}

/**
 * The app's one navigation, always on screen beside whatever view is open (see "Shell" in design-system/MASTER.md).
 * Views on top, workspaces in the middle (they are the list that grows, so they get the scroll), and the two settings
 * destinations pinned to the bottom, away from the everyday items.
 */
export function NavRail({ onNavigate }: { onNavigate?: () => void } = {}) {
  const route = useRoute()
  const active: NavKey = activeNav(route)
  const workspaceId = activeWorkspaceId(route)
  const { railRef, pillRef } = useRailPill(`${active}:${workspaceId ?? ''}`)
  return (
    <nav
      ref={railRef}
      data-glass-area="chrome"
      aria-label="Views"
      onClick={(event) => {
        if ((event.target as HTMLElement).closest('a')) onNavigate?.()
      }}
      className={cn('relative flex min-h-0 flex-col gap-2 border-r border-glass-border p-2', glass)}
    >
      {/* The glass pill on the current page's item. It glides there from the last page's item in 650 ms with a slight
          spring, like the workspace tabs' pill (a Web Animation, `useRailPill`); with reduced motion it jumps. It comes
          first, so the items paint over it, and fades out while its item is scrolled out of view. */}
      <span
        ref={pillRef}
        aria-hidden="true"
        data-rail-pill
        className="pointer-events-none absolute top-0 left-0 rounded-md bg-glass-strong shadow-sm ring-1 ring-glass-border inset-shadow-[0_1px_0_var(--glass-rim)] will-change-transform data-hidden:opacity-0 motion-safe:transition-opacity motion-safe:duration-150"
      />
      <div className="flex flex-col gap-0.5">
        <RailLink href="#/" icon={Library} label="Library" active={active === 'library'} />
        <RailLink href={graphHref} icon={Share2} label="Graph" active={active === 'graph'} />
        <RailLink href={chartsHref} icon={ChartColumn} label="Charts" active={active === 'charts'} />
        <RailLink href={notesHref()} icon={StickyNote} label="Notes" active={active === 'notes'} />
        <RailLink href={referencesHref()} icon={BookMarked} label="References" active={active === 'references'} />
      </div>

      {/* The one part that can outgrow the rail, so it takes the scroll and the pinned items below stay put. */}
      <div data-rail-scroll className="min-h-0 flex-1 overflow-y-auto">
        <WorkspaceSidebar activeId={workspaceId} />
      </div>

      <div className="flex flex-col gap-0.5 border-t border-glass-border pt-2">
        <RailLink href={connectClaudeHref} icon={Plug} label="Connect Claude" active={active === 'connect-claude'} />
        <RailLink href={settingsHref} icon={Settings} label="Settings" active={active === 'settings'} />
      </div>
    </nav>
  )
}
