import { ExternalLink, LoaderCircle, Plus } from 'lucide-react'
import { AlreadyInLibraryError, NoFreePdfError, type Candidate } from '@/api/client'
import { useAddCandidate } from '@/api/queries'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorAlert } from '@/features/library/ErrorAlert'
import { byline } from '@/features/library/paperMeta'
import { codeInWords } from '@/lib/errorWords'
import { readerHref } from '@/lib/route'
import { candidateKey, citationsLabel, pageLink, SOURCE_NAMES } from './candidateMeta'

type RowProps = { candidate: Candidate; workspaceId?: string }

/** One found paper: what it is, its sources, whether a free PDF is listed, and Add or Save without PDF, In library or Open page. */
function CandidateRow({ candidate, workspaceId }: RowProps) {
  const add = useAddCandidate(workspaceId)
  const held = add.error instanceof AlreadyInLibraryError ? add.error.paperId : undefined
  const paperId = add.data?.id ?? held ?? candidate.paper_id
  const hasPdf = candidate.pdf_urls.length > 0
  // No free PDF listed, or Add just found none: the paper can still be saved by its details.
  const canSaveWithoutPdf = !hasPdf || add.error instanceof NoFreePdfError
  const link = pageLink(candidate)
  const meta = [byline(candidate), citationsLabel(candidate.cited_by_count)].filter(Boolean).join(' · ')
  return (
    <li className="candidate-row flex flex-col gap-2 px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p title={candidate.title} className="line-clamp-2 font-heading text-base leading-snug font-semibold wrap-anywhere">
            {candidate.title}
          </p>
          {meta && <p className="mt-0.5 truncate text-sm text-muted-foreground">{meta}</p>}
          {candidate.sources.length > 0 && (
            <ul aria-label="Found by" className="candidate-sources mt-1.5 flex flex-wrap gap-1">
              {candidate.sources.map((source) => (
                <li key={source}>
                  <Badge variant="outline" className="font-normal text-muted-foreground">
                    {SOURCE_NAMES[source]}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Badge variant={hasPdf ? 'secondary' : 'outline'} className="mt-0.5">
          {hasPdf ? 'PDF' : 'No free PDF'}
        </Badge>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {paperId ? (
          <Button size="sm" variant="outline" asChild>
            <a href={readerHref(paperId)}>{held ? 'Already in your library' : 'In library'}</a>
          </Button>
        ) : (
          <>
            {hasPdf && (
              <Button
                size="sm"
                aria-label={`Add ${candidate.title}`}
                disabled={add.isPending}
                onClick={() => add.mutate({ candidate })}
              >
                {add.isPending ? <LoaderCircle aria-hidden className="motion-safe:animate-spin" /> : <Plus aria-hidden />}
                {add.isPending ? 'Adding…' : 'Add'}
              </Button>
            )}
            {canSaveWithoutPdf && (
              <Button
                size="sm"
                variant={hasPdf ? 'outline' : 'default'}
                aria-label={`Save without PDF: ${candidate.title}`}
                disabled={add.isPending}
                onClick={() => add.mutate({ candidate, saveWithoutPdf: true })}
              >
                {add.isPending ? 'Saving…' : 'Save without PDF'}
              </Button>
            )}
          </>
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
      {add.error && !held && <ErrorAlert message={codeInWords(add.error.message)} />}
    </li>
  )
}

type Props = {
  candidates: Candidate[]
  /** Shown instead of the list when there are no candidates. */
  empty: string
  /** Add also files each paper in this workspace. */
  workspaceId?: string
}

/** Found papers, shared by Find papers and the reader's Similar tab. */
export function CandidateList({ candidates, empty, workspaceId }: Props) {
  if (candidates.length === 0) return <p className="text-muted-foreground">{empty}</p>
  return (
    <ul className="candidate-list divide-y divide-glass-border rounded-xl border border-glass-border">
      {candidates.map((candidate, index) => (
        <CandidateRow key={candidateKey(candidate, index)} candidate={candidate} workspaceId={workspaceId} />
      ))}
    </ul>
  )
}
