// What each 3D moment shows for its input (pure, no three.js).
import type { DownloadState } from '@/features/settings/searchModel'
import { clamp01, intro } from './clock'
import type { MarkState } from './parts'

export type DownloadInput = { status: DownloadState['status']; percent: number }

/** Dust gathers to 90% of the mark with the download; at done the intro's second half forms and sweeps the card. */
export function downloadPose({ status, percent }: DownloadInput, sinceDone: number): { gather: number } & MarkState {
  const none = { card: 0, sweep: 0, flash: 0, sheen: 0 }
  if (status === 'done') {
    const k = intro(1.7 + sinceDone) // from the moment the card starts to show
    return { gather: 1, card: k.card, sweep: k.sweep, flash: k.flash, sheen: k.sheen }
  }
  if (status === 'downloading') return { gather: 0.9 * clamp01(percent / 100), ...none }
  return { gather: 0, ...none }
}
