import type { ChartSummary } from '@/api/client'

const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 60 * 60 * 24 * 365],
  ['month', 60 * 60 * 24 * 30],
  ['week', 60 * 60 * 24 * 7],
  ['day', 60 * 60 * 24],
  ['hour', 60 * 60],
  ['minute', 60],
]

export const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`

/** "2 hours ago", down to the minute; "just now" under a minute. `now` is injectable so tests don't chase the clock. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = (Date.parse(iso) - now) / 1000
  for (const [unit, secondsPerUnit] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= secondsPerUnit) return rtf.format(Math.round(seconds / secondsPerUnit), unit)
  }
  return 'just now'
}

/** A chart's line under its title, the same in the list and in the preview: "Used in 2 notes · edited 3 hours ago". */
export const chartMeta = (chart: Pick<ChartSummary, 'note_count' | 'updated_at'>, now?: number) =>
  `Used in ${plural(chart.note_count, 'note')} · edited ${relativeTime(chart.updated_at, now)}`
