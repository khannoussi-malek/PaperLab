import type { EmbeddingStatus } from '@/api/client'
import { describePull } from './pullProgress'

/** Where this tab's download of the built-in search model stands. */
export type DownloadState =
  | { status: 'idle' }
  | { status: 'downloading'; completed: number; total: number }
  | { status: 'done'; papersQueued: number }
  | { status: 'error'; message: string }

/** A whole percentage of the download, 0 until its size is known. */
export function downloadPercent(download: { completed: number; total: number }): number {
  return describePull({ status: 'downloading', ...download }).percent ?? 0
}

/** "Download search model · 138 MB": decimal megabytes of what a download fetches now (the shipped variant's files,
 * minus whatever a stopped download left). */
export function downloadLabel(bytes: number): string {
  return `Download search model · ${Math.round(bytes / 1_000_000)} MB`
}

/** Settings → Search's status line. */
export function statusLine(modelPresent: boolean, download: DownloadState): string {
  if (download.status === 'downloading') return `Search model: downloading… ${downloadPercent(download)}%`
  if (modelPresent || download.status === 'done') return 'Search model: ready'
  return 'Search model: not downloaded'
}

/** A download the API refused before it started (409), as a state: the model is already here, or another tab is
 * downloading it. Any other refusal is shown as the API worded it. */
export function refusedDownload(detail: string): DownloadState {
  if (detail === 'model_present') return { status: 'done', papersQueued: 0 }
  if (detail === 'download_running') return { status: 'error', message: 'The search model is already downloading in another window.' }
  return { status: 'error', message: detail }
}

/** The app root's one polite, visually hidden live region: it must announce a finished download exactly once, even
 * though the button that started it may have already unmounted. Errors announce through their own Alert instead, so
 * this stays silent for every other state, including a still-running download (a live status line would re-read on
 * every percent). */
export function downloadAnnouncement(download: DownloadState): string {
  return download.status === 'done' ? 'Search model downloaded.' : ''
}

/** P1: the library's one quiet line shows while no search model is downloaded and some paper is too long to chat
 * with whole. */
export function showSearchNotice(status: Pick<EmbeddingStatus, 'model_present' | 'papers_needing_search'>): boolean {
  return !status.model_present && status.papers_needing_search > 0
}
