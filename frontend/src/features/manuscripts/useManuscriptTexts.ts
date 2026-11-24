import { useCallback, useMemo, useState } from 'react'
import type { useManuscript } from '@/services/queries'
import { useManuscriptFiles } from '@/services/queries'
import { outline } from '@/features/manuscripts/outline'
import { openRowIndex, sectionRows, sectionText } from '@/features/manuscripts/sections'

type Data = ReturnType<typeof useManuscript>['data']

/** The texts the studio works from: every .tex file (the open one live from the editor), the outline and the section rows. */
export function useManuscriptTexts(manuscriptId: string, data: Data, path: string | undefined, cursor: { path: string; line: number } | null) {
  const [live, setLive] = useState<Record<string, string>>({})
  const onText = useCallback(
    (p: string, text: string | null) =>
      setLive((l) => (text === null ? Object.fromEntries(Object.entries(l).filter(([k]) => k !== p)) : { ...l, [p]: text })),
    [],
  )
  // Same keys as the editor's own query, so the open file is fetched once; the others feed the outline.
  const texFiles = (data?.files ?? []).filter((f) => f.path.endsWith('.tex'))
  const texQueries = useManuscriptFiles(manuscriptId, texFiles.map((f) => f.path))
  const texts = texQueries.map((q) => q.data?.text).join('\u0000')
  const fileTexts = useMemo(() => {
    const files = Object.fromEntries(texFiles.flatMap((f, i) => (texQueries[i].data ? [[f.path, texQueries[i].data.text]] : [])))
    return { ...files, ...live }
  }, [texts, live])
  const allTexts = useMemo(() => Object.values(fileTexts), [fileTexts])
  // The section being written (its key changes when another one is opened), for the deck's order and ranking.
  const section = useMemo(() => {
    if (!data || !path) return { key: '', text: '' }
    const rows = sectionRows(fileTexts, data.main_file, new Set(data.files.map((f) => f.path)))
    const row = rows[openRowIndex(rows, path, cursor && cursor.path === path ? cursor.line : 1)]
    return row && !row.missing ? { key: `${row.path}:${row.line}`, text: sectionText(fileTexts, row) } : { key: path, text: fileTexts[path] ?? '' }
  }, [fileTexts, data, path, cursor])
  const items = useMemo(() => (data ? outline(fileTexts, data.main_file) : []), [data?.main_file, fileTexts])
  const rows = useMemo(() => (data ? sectionRows(fileTexts, data.main_file, new Set(data.files.map((f) => f.path))) : []), [data, fileTexts])
  return { onText, setLive, fileTexts, allTexts, section, items, rows }
}
