import { useQueryClient } from '@tanstack/react-query'
import type { ProvenanceOut } from '@/api/client'
import { useImportSearchHits, usePatchSearchHit, useSearchHit, useUploadHitPdf } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { HitPreview } from '@/features/workspace-search/HitPreview'
import { BranchControl, type BranchTarget } from './BranchControl'
import { isUnknown } from './layout'
import { decisionWord } from './levelText'

type Props = {
  workspaceId: string
  data: ProvenanceOut
  id: string
  busy: boolean
  onFind: (target: { hit_id: string } | { paper_id: string }) => void
}

/** The tree's side panel: a hit opens the Search tab's panel (screening included); a hand-added paper or a
 * "parent not recorded" box shows its title and level. Branch control and the snowball button sit above. */
export function SidePanel({ workspaceId, data, id, busy, onFind }: Props) {
  const node = data.nodes.find((n) => n.id === id)
  const root = data.roots.find((r) => r.id === id)
  const isHit = node !== undefined && !id.startsWith('paper:') && !isUnknown(id)
  const hit = useSearchHit(workspaceId, isHit ? id : null).data
  const client = useQueryClient()
  const review = usePatchSearchHit(workspaceId)
  const importHits = useImportSearchHits(workspaceId)
  const upload = useUploadHitPdf(workspaceId)
  // Screening changes the hit and the tree's colours and branch defaults; re-read them (the hit query hangs off the provenance key).
  const refresh = { onSuccess: () => client.invalidateQueries({ queryKey: ['workspaces', workspaceId, 'search'] }) }

  const target: BranchTarget | null = isHit ? { hit_id: id } : node?.paper_id ? { paper_id: node.paper_id } : null
  return (
    <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-auto rounded-lg border border-border bg-card p-3 text-sm">
      {target && (
        <>
          <BranchControl key={id} workspaceId={workspaceId} target={target} branch={node?.branch} />
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => onFind(target)}>
            {busy ? 'Snowballing…' : 'Find citing & cited papers'}
          </Button>
        </>
      )}
      {hit ? (
        <HitPreview
          hit={hit}
          workspaceId={workspaceId}
          onReview={(hitId, body) => review.mutate({ hitId, body }, refresh)}
          onAddPdf={(hitId) => importHits.mutate([hitId], refresh)}
          addPdfPending={importHits.isPending}
          onUpload={(hitId, file) => upload.mutate({ hitId, file }, refresh)}
          uploadPending={upload.isPending}
        />
      ) : (
        <div>
          <h3 className="font-heading text-base">{node?.title ?? root?.label}</h3>
          {node && (
            <p className="mt-1 text-xs text-muted-foreground">
              {node.year ? `${node.year} · ` : ''}Level {node.level} · {decisionWord(node.decision)}
            </p>
          )}
        </div>
      )}
    </aside>
  )
}
