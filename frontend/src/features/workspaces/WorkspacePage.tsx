import { useEffect, useRef } from 'react'
import { useWorkspace } from '@/api/queries'
import { glass } from '@/components/glass'
import { ModeToggle } from '@/components/mode-toggle'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { workspaceHref, type WorkspaceTab } from '@/lib/route'
import { cn } from '@/lib/utils'
import { WorkspaceChat } from './WorkspaceChat'
import { WorkspaceNotes } from './WorkspaceNotes'
import { WorkspacePapers } from './WorkspacePapers'
import { WorkspaceSidebar } from './WorkspaceSidebar'
import { countsLine } from './workspaceMeta'

// Every tab stays mounted, so each keeps its scroll position across a switch, and fades in each time it is shown,
// like the reader's panels. `text-base` undoes TabsContent's `text-sm`.
const panel = cn('min-h-0 flex-1 overflow-auto text-base data-[state=inactive]:hidden', fadeIn)

/** A workspace's home: its name and counts over Papers, Notes and Chat tabs, with the sidebar beside them. */
export function WorkspacePage({ workspaceId, tab }: { workspaceId: string; tab: WorkspaceTab }) {
  const workspace = useWorkspace(workspaceId)
  // replace, not assign: switching tabs shouldn't add history entries for Back to walk through.
  const showTab = (next: WorkspaceTab) => window.location.replace(workspaceHref(workspaceId, next))
  const title = workspace.data?.name ?? (workspace.data === null ? 'Workspace not found' : 'Loading…')

  // This page swaps in for the library on the same hash-driven route, remounting from scratch (a new
  // WorkspaceSidebar included). Any focus a click or the sidebar's own "New workspace" flow just set is lost with
  // the old tree, so land it here instead: the heading is the one thing every arrival at this page has in common.
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => headingRef.current?.focus(), [])

  return (
    <main className={cn('mx-auto flex h-dvh max-w-7xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1
            ref={headingRef}
            tabIndex={-1}
            // `focus:` (not `focus-visible:`), so this always shows: it's not Tab-reachable, so the only way here is
            // our own arrival focus or a direct click, and `:focus-visible` can go unset for either depending on
            // what the user did just before landing (a mouse click earlier in the flow is enough to suppress it).
            className="truncate rounded-sm font-heading text-3xl font-semibold outline-none focus:ring-3 focus:ring-ring/50"
            title={title}
          >
            {title}
          </h1>
          {workspace.data && (
            <p className="text-sm text-muted-foreground">
              {countsLine(workspace.data.paper_count, workspace.data.note_count)}
            </p>
          )}
        </div>
        <ModeToggle />
      </header>

      <div className="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-4 lg:grid-cols-[14rem_minmax(0,1fr)] lg:grid-rows-1">
        <WorkspaceSidebar activeId={workspaceId} />
        {workspace.error && (
          <Alert variant="destructive" className={cn('self-start border-glass-border', glass)}>
            <AlertDescription>{workspace.error.message}</AlertDescription>
          </Alert>
        )}
        {workspace.data === null && (
          <p className="text-muted-foreground">This workspace doesn't exist. It may have been deleted.</p>
        )}
        {workspace.data && (
          <Tabs value={tab} onValueChange={(value) => showTab(value as WorkspaceTab)} className="min-h-0 min-w-0 gap-3">
            <TabsList>
              <TabsTrigger value="papers">Papers</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="chat">Chat</TabsTrigger>
            </TabsList>
            <TabsContent value="papers" forceMount className={panel}>
              <WorkspacePapers workspaceId={workspaceId} />
            </TabsContent>
            <TabsContent value="notes" forceMount className={panel}>
              <WorkspaceNotes workspaceId={workspaceId} />
            </TabsContent>
            {/* The chat panel scrolls its own answer list and keeps the question box in view. */}
            <TabsContent value="chat" forceMount className={cn(panel, 'flex flex-col overflow-hidden')}>
              <WorkspaceChat workspace={workspace.data} onShowNotes={() => showTab('notes')} />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </main>
  )
}
