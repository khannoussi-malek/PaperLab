import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef } from 'react'
import { api, ApiError } from '@/api/client'
import { MAIN_CHANGED, ensurePackages, preambleEdit, type PreambleEdit } from './insertBlock'

export type InsertResult = { ok: true } | { ok: false; message: string }

type Deps = {
  manuscriptId: string
  mainFile: string | null
  /** The file the editor shows. */
  openPath: string | null
  /** The live text of a file (the editor's buffer when it is open). */
  getText: (path: string) => string | undefined
  /** Whether an editor is open to insert into. */
  hasEditor: () => boolean
  /** The stage 2 cursor-aware insert; with `preamble` that edit goes in the same editor change. False when no editor is open. */
  insert: (text: string, block: boolean, preamble?: PreambleEdit) => boolean
}

const NO_EDITOR = 'Open a .tex file in the editor to insert into.'
const NO_MAIN = 'Open the main file in the editor and try again.'
const GONE = 'The packages were added; insert the block again.'

/**
 * Puts a results block at the cursor on lines of its own, after the main file's preamble has the packages it needs.
 * Main open: the preamble lines and the block are two changes of one editor transaction (atomic, one undo), so
 * neither can overwrite the other. Another file open: a save of main based on its updated_at; a 409 refuses and
 * inserts nothing.
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
      if (d.openPath === d.mainFile) {
        const text = d.getText(d.mainFile)
        if (text === undefined) return { ok: false, message: NO_MAIN } // never a based save under a live buffer
        return d.insert(code, true, preambleEdit(text, packages) ?? undefined) ? { ok: true } : { ok: false, message: NO_EDITOR }
      }
      const fresh = await api.getManuscriptFile(d.manuscriptId, d.mainFile)
      const next = ensurePackages(fresh.text, packages)
      if (!latest.current.hasEditor()) return { ok: false, message: NO_EDITOR } // closed while fetching: still nothing written
      if (next !== null) {
        await api.saveManuscriptFile(d.manuscriptId, d.mainFile, next, fresh.updated_at)
        void queryClient.invalidateQueries({ queryKey: ['manuscripts', d.manuscriptId, 'file', d.mainFile] })
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'file_changed') return { ok: false, message: MAIN_CHANGED }
      return { ok: false, message: e instanceof Error ? e.message : String(e) }
    }
    return latest.current.insert(code, true) ? { ok: true } : { ok: false, message: GONE } // ensurePackages is idempotent: retrying is harmless
  }, [queryClient])
}
