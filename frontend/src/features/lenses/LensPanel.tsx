import type { ReactNode } from 'react'
import { usePaperBriefs, useSetSectionRole } from './queries'
import { ErrorAlert, LoadError } from '@/features/library/ErrorAlert'
import { NO_PDF_LENS_TEXT, lensNotice, lensSections } from './lenses'
import { BriefCard } from './BriefCard'
import { SectionRow } from './SectionRow'
import { useBriefStream } from './useBriefStream'
import type { LensReader } from './useLensReader'

// hasPdf: the paper has its PDF. A paper without one has no sections, so the tab says so and nothing else (R1).
type Props = { paperId: string; reader: LensReader; hasPdf: boolean }

/** The Lens tab (spec §5): the lens's label, what it can't show, then its sections, each with Change role. */
export function LensPanel({ paperId, reader, hasPdf }: Props) {
  const setRole = useSetSectionRole(paperId)
  const briefs = usePaperBriefs(paperId)
  const { stream, generate } = useBriefStream(paperId)
  const { lens, sectionsQuery } = reader
  if (!hasPdf) return <Shell><p className="lens-notice text-sm text-muted-foreground">{NO_PDF_LENS_TEXT}</p></Shell>
  if (sectionsQuery.error) {
    return (
      <Shell>
        <LoadError message={sectionsQuery.error.message} onRetry={() => void sectionsQuery.refetch()} />
      </Shell>
    )
  }
  if (!lens) return <Shell><p role="status" className="text-sm text-muted-foreground">Reading the sections…</p></Shell>
  const notice = lensNotice(lens, hasPdf)
  return (
    <Shell>
      <h2 className="font-heading text-lg font-semibold">{lens.label}</h2>
      {notice && <p className="lens-notice text-sm text-muted-foreground">{notice.text}</p>}
      {lens.id !== 'full' && notice?.kind !== 'empty' && (
        briefs.error ? (
          <LoadError message={briefs.error.message} onRetry={() => void briefs.refetch()} />
        ) : briefs.isPending ? (
          // Same height as the idle card's line, so the card doesn't jump when the briefs arrive.
          <p role="status" className="min-h-20 text-sm text-muted-foreground">Looking for a saved brief…</p>
        ) : (
          <BriefCard
            lens={lens}
            saved={briefs.data?.find((brief) => brief.lens === lens.id) ?? null}
            stream={stream}
            onGenerate={() => void generate(lens.id, lens.label)}
            onCite={(source) => reader.jump(source.page, source.bbox)}
          />
        )
      )}
      {setRole.error && <ErrorAlert message={setRole.error.message} />}
      <ul aria-label="Sections" className="lens-sections flex flex-col gap-0.5">
        {lensSections(reader.sections, lens).map((section) => (
          <SectionRow
            key={section.first_chunk_id}
            section={section}
            busy={setRole.isPending}
            onJump={() => reader.jumpToChunk(section.first_chunk_id)}
            onRoleChange={(role) => section.title !== null && setRole.mutate({ section_title: section.title, role })}
          />
        ))}
      </ul>
    </Shell>
  )
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <aside aria-label="Lens" className="lens-panel flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 pt-3 pb-4">
      {children}
    </aside>
  )
}
