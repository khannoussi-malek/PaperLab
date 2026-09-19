/** main.log (spec §5): every docker command and its exit code, and what the app logs instead of showing. */
import { appendFileSync, existsSync, mkdirSync, statSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'

export const LOG_LIMIT = 1_000_000

export type Log = (line: string) => void

/** Appends one timestamped line; a file past LOG_LIMIT starts over. Never throws: a log that can't be written is no
 * reason to stop PaperLab, so that failure goes to stderr instead. */
export function fileLog(path: string, now: () => Date = () => new Date()): Log {
  return (line) => {
    try {
      mkdirSync(dirname(path), { recursive: true })
      if (existsSync(path) && statSync(path).size > LOG_LIMIT) writeFileSync(path, '')
      appendFileSync(path, `${now().toISOString()} ${line}\n`)
    } catch (error) {
      console.error('PaperLab could not write its log', error)
    }
  }
}
