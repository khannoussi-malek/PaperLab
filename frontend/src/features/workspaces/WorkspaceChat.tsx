import type { ChatSource, NoteSource, Workspace } from '@/api/client'
import { usePapers, useWorkspacePapers } from '@/api/queries'
import { glass } from '@/components/glass'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { paperLabel } from '@/features/library/paperMeta'
import { chunkHref, noteHref } from '@/lib/route'
import { cn } from '@/lib/utils'
import { countsLine } from './workspaceMeta'

type Props = {
  workspace: Workspace
  /** A promoted note is listed on the Notes tab. */
  onShowNotes: () => void
}

/** The Chat tab: the reader's chat panel over the whole workspace, under a line saying what it covers. */
export function WorkspaceChat({ workspace, onShowNotes }: Props) {
  const members = useWorkspacePapers(workspace.id)
  // Labels come from the library, so a source whose paper has since left the workspace keeps its name.
  const library = usePapers()
  const notIndexed = (members.data ?? []).filter((paper) => paper.status !== 'ready').length

  function labelOf(paperId: string) {
    const paper = library.data?.find((p) => p.id === paperId)
    return paper ? paperLabel(paper) : 'Deleted paper'
  }

  // assign, not replace: Back returns from the reader to this answer.
  function openSource(source: ChatSource | NoteSource) {
    window.location.hash =
      'note_id' in source
        ? noteHref(source.paper_id, source.note_id)
        : chunkHref(source.paper_id, source.chunk_id, source.page)
  }

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col rounded-xl ring-1 ring-glass-border', glass)}>
      <p className="chat-scope border-b border-glass-border px-4 py-2 text-sm text-muted-foreground">
        {countsLine(workspace.paper_count, workspace.note_count, notIndexed)}
      </p>
      <ChatPanel
        scope={{ kind: 'workspace', id: workspace.id }}
        unavailable={workspace.paper_count === 0 ? 'Add papers to chat with this workspace.' : undefined}
        paperLabel={labelOf}
        onCite={openSource}
        onPromoted={onShowNotes}
      />
    </div>
  )
}
