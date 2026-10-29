import { api, ApiError } from '@/api/client'
import type { ReviewHandle } from './reviewMarks'

export const CHANGED = 'That sentence changed. Check again.'

/** Pins the paper (adding it to the workspace first if the library doesn't hold it), then inserts `\citep{key}`. Returns a problem to show, or null. */
export async function citeThis(
  { manuscriptId, workspaceId, handle }: { manuscriptId: string; workspaceId: string | null; handle: Pick<ReviewHandle, 'applyCite'> | null },
  hash: string,
  paperId: string,
): Promise<string | null> {
  if (!handle) return 'The editor is not ready. Try again.'
  let key: string
  try {
    try {
      key = (await api.pinPaper(manuscriptId, paperId)).key
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404 && e.code.startsWith('unknown_paper') && workspaceId)) throw e
      await api.addToWorkspace(workspaceId, paperId)
      key = (await api.pinPaper(manuscriptId, paperId)).key
    }
  } catch (e) {
    return `Couldn't add that paper to the bibliography${e instanceof Error ? `: ${e.message}` : '.'}`
  }
  try {
    return (await handle.applyCite(hash, key)) === 'ok' ? null : CHANGED
  } catch (e) {
    return e instanceof Error ? e.message : 'Something went wrong. Please try again.'
  }
}
