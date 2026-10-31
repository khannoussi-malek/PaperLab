import { useChunksOnPage } from '@/api/queries'
import { usePaperSections } from '@/features/lenses/queries'

const MAX_CHARS = 900
const WANTED = [
  { role: 'conclusion', title: 'Conclusion' },
  { role: 'discussion', title: 'Discussion' },
] as const

export type Conclusion = {
  status: 'loading' | 'ready' | 'none' | 'error'
  title: string
  page: number | null
  text: string
  /** The paper's sections came back empty: its full text isn't read in yet. */
  noSections: boolean
}

/** The paper's conclusion (else discussion), from the page's own chunks: section previews are too short to judge by. */
export function useConclusion(paperId: string, enabled: boolean): Conclusion {
  const sections = usePaperSections(paperId, enabled)
  const list = sections.data?.sections ?? []
  const found = WANTED.map((w) => ({ w, s: list.find((s) => s.role === w.role) })).find((x) => x.s)
  const chunks = useChunksOnPage(paperId, found?.s?.page ?? null)
  const none: Conclusion = { status: 'none', title: '', page: null, text: '', noSections: false }
  if (!enabled) return none
  if (sections.error || chunks.error) return { ...none, status: 'error' }
  if (sections.isPending || (found && chunks.isPending)) return { ...none, status: 'loading' }
  if (!found?.s) return { ...none, noSections: list.length === 0 }
  const ids = new Set(found.s.chunk_ids)
  const full = (chunks.data ?? [])
    .filter((c) => ids.has(c.id))
    .sort((a, b) => a.ordinal - b.ordinal)
    .map((c) => c.text.trim())
    .join(' ')
  if (!full) return { ...none, noSections: false }
  const text = full.length > MAX_CHARS ? `${full.slice(0, MAX_CHARS)}…` : full
  return { status: 'ready', title: found.w.title, page: found.s.page, text, noSections: false }
}
