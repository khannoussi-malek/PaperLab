import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef } from 'react'
import { api, ApiError } from '@/api/client'
import { MAIN_CHANGED, ensurePackages } from './insertBlock'

export type InsertResult = { ok: true } | { ok: false; message: string }

type Deps = {
  manuscriptId: string
  mainFile: string | null
  /** The file the editor shows. */
  openPath: string | null
  /** The live text of a file (the editor's buffer when it is open). */
  getText: (path: string) => string | undefined
  /** An edit of the open editor's buffer at a 1-based line and 0-based column. */
  replace: (line: number, col: number, text: string) => void
  canReplace: () => boolean
  hasEditor: () => boolean
  /** The stage 2 cursor-aware insert; false when no editor is open. */
  insert: (text: string, block: boolean) => boolean
}

const NO_EDITOR = 'Open a .tex file in the editor to insert into.'
const BEGIN = '\\begin{document}'

/**
 * Puts a results block at the cursor on lines of its own, after the main file's preamble has the packages it needs.
 * The preamble edit is conflict-safe like the PDF edit box's: the editor buffer when main is open, else a save based
 * on the file's updated_at; a 409 refuses and inserts nothing.
 */
export function useInsertBlock(deps: Deps): (code: string, packages: string[]) => Promise<InsertResult> {
  const queryClient = useQueryClient()
  const latest = useRef(deps)
  latest.current = deps
  return useCallback(async (code, packages) => {
    const d = latest.current
    if (!d.mainFile) return { ok: false, message: 'The manuscript is still loading.' }
    if (!d.hasEditor()) return { ok: false, message: NO_EDITOR } // before anything is written
    try {
      if (d.openPath === d.mainFile && d.canReplace()) {
        const text = d.getText(d.mainFile) ?? ''
        const next = ensurePackages(text, packages)
        if (next !== null) {
          const at = text.indexOf(BEGIN)
          const lines = text.slice(0, at).split('\n')
          const col = lines[lines.length - 1].length
          d.replace(lines.length, col, next.slice(at, at + next.length - text.length))
        }
      } else {
        const fresh = await api.getManuscriptFile(d.manuscriptId, d.mainFile)
        const next = ensurePackages(fresh.text, packages)
        if (next !== null) {
          await api.saveManuscriptFile(d.manuscriptId, d.mainFile, next, fresh.updated_at)
          void queryClient.invalidateQueries({ queryKey: ['manuscripts', d.manuscriptId, 'file', d.mainFile] })
        }
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'file_changed') return { ok: false, message: MAIN_CHANGED }
      return { ok: false, message: e instanceof Error ? e.message : String(e) }
    }
    return latest.current.insert(code, true) ? { ok: true } : { ok: false, message: NO_EDITOR }
  }, [queryClient])
}
