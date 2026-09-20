import { ChartColumn, Library, Plug, Settings, Share2, type LucideIcon } from 'lucide-react'
import { glass } from '@/components/glass'
import { activeNav, activeWorkspaceId, railItem, type NavKey } from '@/components/nav'
import { WorkspaceSidebar } from '@/features/workspaces/WorkspaceSidebar'
import { chartsHref, connectClaudeHref, graphHref, settingsHref, useRoute } from '@/lib/route'
import { cn } from '@/lib/utils'

function RailLink({ href, icon: Icon, label, active }: { href: string; icon: LucideIcon; label: string; active: boolean }) {
  return (
    <a href={href} aria-current={active ? 'page' : undefined} className={railItem(active)}>
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
export function NavRail() {
  const route = useRoute()
  const active: NavKey = activeNav(route)
  return (
    <nav
      aria-label="Views"
      className={cn('flex min-h-0 flex-col gap-2 border-r border-glass-border p-2', glass)}
    >
      <div className="flex flex-col gap-0.5">
        <RailLink href="#/" icon={Library} label="Library" active={active === 'library'} />
        <RailLink href={graphHref} icon={Share2} label="Graph" active={active === 'graph'} />
        <RailLink href={chartsHref} icon={ChartColumn} label="Charts" active={active === 'charts'} />
      </div>

      {/* The one part that can outgrow the rail, so it takes the scroll and the pinned items below stay put. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <WorkspaceSidebar activeId={activeWorkspaceId(route)} />
      </div>

      <div className="flex flex-col gap-0.5 border-t border-glass-border pt-2">
        <RailLink href={connectClaudeHref} icon={Plug} label="Connect Claude" active={active === 'connect-claude'} />
        <RailLink href={settingsHref} icon={Settings} label="Settings" active={active === 'settings'} />
      </div>
    </nav>
  )
}
