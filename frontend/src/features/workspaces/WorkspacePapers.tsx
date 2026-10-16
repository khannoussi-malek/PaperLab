import { FileText, Plus } from 'lucide-react'
import { useState } from 'react'
import { usePaperTags, useTags, useUploadPapers, useWorkspacePapers } from '@/api/queries'
import { delayedIn } from '@/components/motion'
import { Button } from '@/components/ui/button'
import { FindPapersButton } from '@/features/discovery/FindPapersButton'
import { ErrorAlert, LoadError } from '@/features/library/ErrorAlert'
import { PaperList } from '@/features/library/PaperList'
import { UploadPdfsButton } from '@/features/library/UploadPdfsButton'
import type { TagMatch } from '@/lib/route'
import { cn } from '@/lib/utils'
import { AddPapersDialog } from './AddPapersDialog'
import { TagFilterMenu } from './TagFilterMenu'
import { TagPicker } from './TagPicker'
import { TagSidebar } from './TagSidebar'
import { filterByTags, toggled } from './tagFilter'

/** The Papers tab: the library's rows for this workspace's papers, plus adding from the library or by upload. */
export function WorkspacePapers({
  workspaceId,
  tags,
  match,
  onTagsChange,
}: {
  workspaceId: string
  tags: string[]
  match: TagMatch
  onTagsChange: (tags: string[], match: TagMatch) => void
}) {
  const papers = useWorkspacePapers(workspaceId)
  const tagList = useTags(workspaceId)
  const paperTags = usePaperTags(workspaceId)
  const tagMap = paperTags.data ?? {}
  const upload = useUploadPapers(workspaceId)
  const [adding, setAdding] = useState(false)
  const [visible, setVisible] = useState<string[] | null>(null)
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set())

  const all = papers.data
  // Until both tag queries have answered the list is unfiltered: an empty map would otherwise empty it.
  const list = all && (tagList.data && paperTags.data ? filterByTags(all, tagMap, tags, match, tagList.data.map((t) => t.name)) : all)
  // Only papers still on screen stay selected: the tag filter and the list's own search both can hide some.
  const selectedIds = (list ?? []).filter((p) => picked.has(p.id) && (visible?.includes(p.id) ?? true)).map((p) => p.id)
  const toggle = (id: string) => setPicked((prev) => new Set(prev.has(id) ? [...prev].filter((x) => x !== id) : [...prev, id]))
  const filterProps = { workspaceId, selected: tags, match, onChange: onTagsChange }
  return (
    <div className="flex flex-col gap-4 py-2">
      <div className="flex items-center gap-2">
        <Button onClick={() => setAdding(true)}>
          <Plus aria-hidden />
          Add papers
        </Button>
        <UploadPdfsButton variant="outline" isPending={upload.isPending} onUpload={(files) => upload.mutate(files)} />
        <FindPapersButton workspaceId={workspaceId} />
      </div>

      {upload.error && <ErrorAlert message={upload.error.message} />}

      {list === undefined ? (
        papers.isError ? (
          <LoadError message={papers.error.message} onRetry={() => void papers.refetch()} />
        ) : (
          <p className={cn('text-muted-foreground', delayedIn)}>Loading…</p>
        )
      ) : all?.length === 0 ? (
        <div className="grid place-items-center gap-2 rounded-xl border border-dashed border-glass-border px-6 py-16 text-center">
          <FileText aria-hidden className="size-8 text-muted-foreground" />
          <p className="text-muted-foreground">No papers in this workspace yet. Add them from your library, or upload a PDF.</p>
        </div>
      ) : (
        <div className="flex items-start gap-6">
          <TagSidebar {...filterProps} />
          <div className="flex min-w-0 flex-1 flex-col gap-3">
            <TagFilterMenu {...filterProps} />
            {selectedIds.length > 0 && (
              <div className="flex items-center gap-2">
                <span role="status" className="text-sm">{selectedIds.length} selected</span>
                <TagPicker workspaceId={workspaceId} mode="add" paperIds={selectedIds} onDone={() => setPicked(new Set())} />
                <TagPicker workspaceId={workspaceId} mode="remove" paperIds={selectedIds} onDone={() => setPicked(new Set())} />
                <Button variant="ghost" size="sm" onClick={() => setPicked(new Set())}>Clear</Button>
              </div>
            )}
            <PaperList
              selection={{ selected: new Set(selectedIds), onToggle: toggle }}
              papers={list}
              onVisibleChange={setVisible}
              workspaceId={workspaceId}
              tagsByPaper={tagMap}
              activeTags={tags}
              emptyMessage={`No papers carry ${match === 'all' ? 'all of' : 'any of'} those tags.`}
              onTagClick={(name) => !tags.includes(name) && onTagsChange(toggled(tags, name), match)}
            />
          </div>
        </div>
      )}

      <AddPapersDialog workspaceId={workspaceId} open={adding} onOpenChange={setAdding} />
    </div>
  )
}
