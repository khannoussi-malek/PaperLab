import { useEffect, useRef } from 'react'
import { useWorkspace } from '@/api/queries'
import { AppShell, shellTitle } from '@/components/AppShell'
import { glass } from '@/components/glass'
import { delayedIn, fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ManualAcquisitionTab } from '@/features/workspace-search/ManualAcquisitionTab'
import { SearchTab } from '@/features/workspace-search/SearchTab'
import { workspaceHref, type WorkspaceTab } from '@/lib/route'
import { cn } from '@/lib/utils'
import { WorkspaceChat } from './WorkspaceChat'
import { WorkspaceNotes } from './WorkspaceNotes'
import { WorkspacePapers } from './WorkspacePapers'
import { countsLine } from './workspaceMeta'

// Every tab stays mounted, so each keeps its scroll position across a switch, and fades in each time it is shown,
// like the reader's panels. `text-base` undoes TabsContent's `text-sm`.
const panel = cn('min-h-0 flex-1 overflow-auto text-base data-[state=inactive]:hidden', fadeIn)

/** A workspace's home: its name and counts over Papers, Notes and Chat tabs, inside the app shell. */
export function WorkspacePage({ workspaceId, tab }: { workspaceId: string; tab: WorkspaceTab }) {
  const workspace = useWorkspace(workspaceId)
  // replace, not assign: switching tabs shouldn't add history entries for Back to walk through.
  const showTab = (next: WorkspaceTab) => window.location.replace(workspaceHref(workspaceId, next))
  const title = workspace.data?.name ?? (workspace.data === null ? 'Workspace not found' : 'Loading…')

  // The page is keyed by workspace, so opening another one remounts it from scratch and whatever a click or the
  // rail's own "New workspace" flow just focused is gone with the old tree. Land focus on the heading instead: it's
  // the one thing every arrival at this page has in common.
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => headingRef.current?.focus(), [])

  return (
    <AppShell
      fills
      title={
        <h1
          ref={headingRef}
          tabIndex={-1}
          // `focus:` (not `focus-visible:`), so this always shows: it's not Tab-reachable, so the only way here is
          // our own arrival focus or a direct click, and `:focus-visible` can go unset for either depending on
          // what the user did just before landing (a mouse click earlier in the flow is enough to suppress it).
          className={cn(
            shellTitle,
            'rounded-sm py-0.5 outline-none focus:ring-3 focus:ring-ring/50',
            workspace.data === undefined && delayedIn,
          )}
          title={title}
        >
          {title}
        </h1>
      }
      status={workspace.data && countsLine(workspace.data.paper_count, workspace.data.note_count)}
    >
      {workspace.error && (
        <Alert variant="destructive" className={cn('self-start border-glass-border', glass)}>
          <AlertDescription>{workspace.error.message}</AlertDescription>
        </Alert>
      )}
      {workspace.data === null && (
        <p className="text-muted-foreground">This workspace doesn't exist. It may have been deleted.</p>
      )}
      {workspace.data && (
        <Tabs value={tab} onValueChange={(value) => showTab(value as WorkspaceTab)} className="min-h-0 min-w-0 flex-1 gap-3">
          <TabsList>
            <TabsTrigger value="papers">Papers</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="search">Search</TabsTrigger>
            <TabsTrigger value="acquisition">Manual acquisition</TabsTrigger>
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
          <TabsContent value="search" forceMount className={panel}>
            <SearchTab workspaceId={workspaceId} />
          </TabsContent>
          <TabsContent value="acquisition" forceMount className={panel}>
            <ManualAcquisitionTab workspaceId={workspaceId} />
          </TabsContent>
        </Tabs>
      )}
    </AppShell>
  )
}
