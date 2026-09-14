import { useWorkspace } from '@/api/queries'
import { glass } from '@/components/glass'
import { ModeToggle } from '@/components/mode-toggle'
import { fadeIn } from '@/components/motion'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { workspaceHref, type WorkspaceTab } from '@/lib/route'
import { cn } from '@/lib/utils'
import { WorkspaceNotes } from './WorkspaceNotes'
import { WorkspacePapers } from './WorkspacePapers'
import { WorkspaceSidebar } from './WorkspaceSidebar'
import { countsLine } from './workspaceMeta'

// Every tab stays mounted, so each keeps its scroll position across a switch, and fades in each time it is shown,
// like the reader's panels. `text-base` undoes TabsContent's `text-sm`.
const panel = cn('min-h-0 flex-1 overflow-auto text-base data-[state=inactive]:hidden', fadeIn)

/** A workspace's home: its name and counts over Papers and Notes tabs, with the sidebar beside them. */
export function WorkspacePage({ workspaceId, tab }: { workspaceId: string; tab: WorkspaceTab }) {
  const workspace = useWorkspace(workspaceId)
  // replace, not assign: switching tabs shouldn't add history entries for Back to walk through.
  const showTab = (next: WorkspaceTab) => window.location.replace(workspaceHref(workspaceId, next))
  const title = workspace.data?.name ?? (workspace.data === null ? 'Workspace not found' : 'Loading…')

  return (
    <main className={cn('mx-auto flex h-dvh max-w-7xl flex-col gap-4 px-4 py-6', fadeIn)}>
      <header className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="truncate font-heading text-3xl font-semibold" title={title}>
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
            </TabsList>
            <TabsContent value="papers" forceMount className={panel}>
              <WorkspacePapers workspaceId={workspaceId} />
            </TabsContent>
            <TabsContent value="notes" forceMount className={panel}>
              <WorkspaceNotes workspaceId={workspaceId} />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </main>
  )
}
