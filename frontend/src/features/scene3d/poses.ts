// What each 3D moment shows for its input (pure, no three.js).
import type { DownloadState } from '@/features/settings/searchModel'
import { clamp01, intro, INTRO_FORMED, out, progress, sheenEvery } from './clock'
import type { MarkState } from './parts'

export type DownloadInput = { status: DownloadState['status'] | 'ready'; percent: number }

/** Dust gathers to 90% of the mark with the download; at done the intro's second half forms and sweeps the card. */
export function downloadPose({ status, percent }: DownloadInput, sinceDone: number): { gather: number } & MarkState {
  const none = { card: 0, sweep: 0, flash: 0, sheen: 0 }
  if (status === 'ready') {
    const k = intro(INTRO_FORMED) // the model was already there: the finished mark, no replay
    return { gather: 1, card: k.card, sweep: k.sweep, flash: k.flash, sheen: k.sheen }
  }
  if (status === 'done') {
    const k = intro(1.7 + sinceDone) // from the moment the card starts to show
    return { gather: 1, card: k.card, sweep: k.sweep, flash: k.flash, sheen: k.sheen }
  }
  if (status === 'downloading') return { gather: 0.9 * clamp01(percent / 100), ...none }
  return { gather: 0, ...none }
}

export type LibraryInput = { uploading: boolean }
/** One upload round: three cards fly in 0.45 s apart, 0.6 s each, then a pause before the next round. */
const ROUND = 2.4

export function libraryPose(t: number, sinceUpload: number | null): { sheen: number; landed: [number, number, number] } {
  const u = sinceUpload === null ? -1 : sinceUpload % ROUND
  const land = (i: number) => (u < 0 ? 0 : out(progress(u, i * 0.45, 0.6)))
  return { sheen: sheenEvery(t), landed: [land(0), land(1), land(2)] }
}
