import { Bookmark, BookmarkCheck, ExternalLink, LoaderCircle, Plus } from 'lucide-react'
import type { Reference, ReferencesDirection } from '@/api/client'
import { useImportReference, useQueueReference } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { citationsLabel, pageLink } from '@/features/discovery/candidateMeta'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { byline } from '@/features/library/paperMeta'
import { readerHref } from '@/lib/route'
import { cocitationBadge, rowAction } from './referencesMeta'

type Props = { reference: Reference; direction: ReferencesDirection; workspaceId?: string; onUnqueued?: () => void }

/** One reference or citing work: what it is, ranking badges, and Import, In library or Open page. */
export function ReferenceRow({ reference, direction, workspaceId, onUnqueued }: Props) {
  const importRef = useImportReference()
  const queueRef = useQueueReference(onUnqueued)
  const inLibraryId = importRef.data?.id ?? reference.paper_id
  const action = rowAction({ ...reference, paper_id: inLibraryId })
  // ReferenceOut still carries flat id fields (not yet migrated to external_ids); translate for pageLink.
  const link = pageLink({
    doi: reference.doi,
    external_ids: {
      ...(reference.arxiv_id ? { arxiv: reference.arxiv_id } : {}),
      ...(reference.openalex_id ? { openalex: reference.openalex_id } : {}),
      ...(reference.s2_id ? { semantic_scholar: reference.s2_id } : {}),
    },
  })
  const meta = [byline(reference), citationsLabel(reference.cited_by_count)].filter(Boolean).join(' · ')
  const badge = cocitationBadge(reference.cocitation, direction)
  const queued = queueRef.isPending ? queueRef.variables.queue : reference.queued_at !== null
  return (
    <li className="reference-row flex flex-col gap-2 px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p title={reference.title} className="line-clamp-2 font-heading text-base leading-snug font-semibold wrap-anywhere">
            {reference.title}
          </p>
          {meta && <p className="mt-0.5 truncate text-sm text-muted-foreground">{meta}</p>}
          {badge && (
            <Badge variant="outline" className="mt-1.5 font-normal text-muted-foreground">
              {badge}
            </Badge>
          )}
        </div>
        <Badge variant={reference.has_pdf ? 'secondary' : 'outline'} className="mt-0.5">
          {reference.has_pdf ? 'PDF' : 'No free PDF'}
        </Badge>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {action === 'in-library' && inLibraryId && (
          <Button size="sm" variant="outline" asChild>
            <a href={readerHref(inLibraryId)}>In library</a>
          </Button>
        )}
        {action === 'import' && (
          <Button
            size="sm"
            aria-label={`Import ${reference.title}`}
            disabled={importRef.isPending}
            onClick={() => importRef.mutate({ refId: reference.id, workspaceId })}
          >
            {importRef.isPending ? <LoaderCircle aria-hidden className="motion-safe:animate-spin" /> : <Plus aria-hidden />}
            {importRef.isPending ? 'Importing…' : 'Import'}
          </Button>
        )}
        {action !== 'in-library' && (
          <Button
            size="sm"
            variant="outline"
            aria-pressed={queued}
            aria-label={`To read: ${reference.title}`}
            aria-disabled={queueRef.isPending}
            className="aria-pressed:border-primary aria-pressed:bg-primary/10 aria-pressed:text-primary aria-disabled:opacity-50"
            onClick={() => !queueRef.isPending && queueRef.mutate({ refId: reference.id, queue: !queued })}
          >
            {queued ? <BookmarkCheck aria-hidden /> : <Bookmark aria-hidden />}
            To read
          </Button>
        )}
        {link && (
          <Button size="sm" variant="ghost" asChild>
            <a href={link} target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden />
              Open page
            </a>
          </Button>
        )}
      </div>
      {importRef.error && <ErrorAlert message={importRef.error.message} />}
      {queueRef.error && <ErrorAlert message={queueRef.error.message} />}
    </li>
  )
}
