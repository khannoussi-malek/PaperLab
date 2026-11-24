import { useMemo, type Dispatch, type SetStateAction } from 'react'
import { manuscriptHref } from '@/router/route'
import { jumpTargets, type Target } from '@/features/manuscripts/jumpTargets'
import { openRowIndex, type SectionRow } from '@/features/manuscripts/sections'
import type { useManuscript, useManuscriptPapers } from '@/services/queries'

type Data = ReturnType<typeof useManuscript>['data']

/** Moving the studio to a file, line or section, and the targets the jump palette offers. A jump in another file navigates there. */
export function useStudioNavigation({ manuscriptId, data, path, cursorLine, rows, items, fileTexts, papers, setJump, showInPdf, showCited }: {
  manuscriptId: string
  data: Data
  path: string | undefined
  cursorLine: number
  rows: SectionRow[]
  items: Parameters<typeof jumpTargets>[1]
  fileTexts: Record<string, string>
  papers: ReturnType<typeof useManuscriptPapers>['data']
  setJump: Dispatch<SetStateAction<{ line: number; n: number } | null>>
  showInPdf: (f: string, ln: number) => void
  showCited: (key: string) => void
}) {
  const jumpTo = (f: string, line: number) => {
    if (f === path) { setJump((j) => ({ line, n: (j?.n ?? 0) + 1 })); showInPdf(f, line) }
    else window.location.assign(manuscriptHref(manuscriptId, f, line))
  }
  const targets = useMemo(() => jumpTargets(rows, items, fileTexts, papers ?? []), [rows, items, fileTexts, papers])
  const singleFile = rows.length > 0 && rows.every((r) => r.inMain)
  const pick = (t: Target) => (t.kind === 'paper' ? showCited(t.key) : jumpTo(t.file, t.line))
  const openSection = (row: SectionRow) => jumpTo(row.path, row.inMain ? row.line : 1)
  const stepSection = (step: -1 | 1) => {
    if (!data || !path) return
    const at = openRowIndex(rows, path, cursorLine)
    const next = rows[at === -1 && step === 1 ? 0 : at + step]
    if (next && !next.missing) openSection(next)
  }
  return { jumpTo, targets, singleFile, pick, openSection, stepSection }
}
