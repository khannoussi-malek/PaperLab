import type { ReactNode } from 'react'
import { useSetSectionRole } from './queries'
import { ErrorAlert, LoadError } from '@/features/library/ErrorAlert'
import { NO_PDF_LENS_TEXT, lensNotice, lensSections } from './lenses'
import { SectionRow } from './SectionRow'
import type { LensReader } from './useLensReader'

// hasPdf: the paper has its PDF. A paper without one has no sections, so the tab says so and nothing else (R1).
type Props = { paperId: string; reader: LensReader; hasPdf: boolean }

/** The Lens tab (spec §5): the lens's label, what it can't show, then its sections, each with Change role. */
export function LensPanel({ paperId, reader, hasPdf }: Props) {
  const setRole = useSetSectionRole(paperId)
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
