import { ExternalLink, LoaderCircle, Plus } from 'lucide-react'
import type { Reference } from '@/api/client'
import { useImportReference } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { citationsLabel, pageLink } from '@/features/discovery/candidateMeta'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { byline } from '@/features/library/paperMeta'
import { readerHref } from '@/lib/route'
import { cocitationBadge, rowAction } from './referencesMeta'

type Props = { paperId: string; reference: Reference; workspaceId?: string }

/** One reference or citing work: what it is, ranking badges, and Import, In library or Open page. */
export function ReferenceRow({ paperId, reference, workspaceId }: Props) {
  const importRef = useImportReference(paperId)
  const inLibraryId = importRef.data?.id ?? reference.paper_id
  const action = rowAction({ ...reference, paper_id: inLibraryId })
  const link = pageLink({ ...reference, core_id: null })
  const meta = [byline(reference), citationsLabel(reference.cited_by_count)].filter(Boolean).join(' · ')
  const badge = cocitationBadge(reference.cocitation)
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
    </li>
  )
}
