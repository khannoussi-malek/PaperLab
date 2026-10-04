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

export type ChatInput = { phase: 'sources' | 'thinking' }
/** Seconds per loop: quicker while finding sources, calmer while the model writes. */
export const CHAT_LOOP = { sources: 1.6, thinking: 2.4 }

export function chatPose(phase: ChatInput['phase'], t: number) {
  const u = (t % CHAT_LOOP[phase]) / CHAT_LOOP[phase]
  return {
    wire: out(progress(u, 0, 0.35)), // the wire lifts off the highlighted line
    note: out(progress(u, 0.3, 0.35)), // and pulls a note up
    light: Math.sin(Math.PI * progress(u, 0.6, 0.3)), // the light lands on it
    fade: 1 - progress(u, 0.9, 0.1), // and it all fades before the next loop
  }
}

export type SearchRunStatus = 'running' | 'exhausted' | 'stopped' | 'failed'

/**
 * A search run has no percent to show (the backend pages sources until each is exhausted, with no "total expected"
 * to divide by) — so this is ambient, not a fill level: a slow breathing while it runs, a calm rest once it ends
 * cleanly (exhausted and stopped read the same — both are a benign "done"), and the dust drifting back out on a
 * failure. The director glides toward these targets with `approach`, the same as `downloadPose`'s percent.
 */
export function searchRunPose(status: SearchRunStatus, t: number): { gather: number; sheen: number; scatter: number } {
  if (status === 'running') return { gather: 0.5 + 0.15 * Math.sin(t * 0.8), sheen: Math.max(0, Math.sin(t * 0.5)), scatter: 0 }
  if (status === 'failed') return { gather: 0.15, sheen: 0, scatter: 1 } // mirrors downloadPose's own error: dust scatters back out
  return { gather: 0.97, sheen: 0, scatter: 0 } // exhausted/stopped: a calm resting state, no transition needed
}
