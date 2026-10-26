import type { ManuscriptDetail } from '@/api/client'

export type CompileError = { file: string; line: number | null; message: string; kind: string }

const isCompileError = (e: unknown): e is CompileError =>
  typeof e === 'object' && e !== null && typeof (e as CompileError).file === 'string' && typeof (e as CompileError).message === 'string'

export const parseCompileErrors = (errors: readonly unknown[] | null | undefined): CompileError[] =>
  (errors ?? []).filter(isCompileError)

/** The messages that point at a line of `file`, for the editor's gutter. */
export const errorsFor = (errors: readonly unknown[] | null | undefined, file: string) =>
  parseCompileErrors(errors).flatMap((e) => (e.file === file && typeof e.line === 'number' ? [{ line: e.line, message: e.message }] : []))

const FRIENDLY = ['needs_download', 'biber_unsupported', 'compile_timeout', 'outside_file']

/**
 * Which friendly sentence a failed compile gets. The worker stores only the log and the error list, not the code it
 * worked out, so this reads the same phrases back; a failure with an empty log is the one-minute stop.
 */
export function friendlyCompileCode(m: Pick<ManuscriptDetail, 'compile_status' | 'compile_log' | 'compile_errors'>): string | null {
  if (m.compile_status !== 'failed') return null
  const byKind = parseCompileErrors(m.compile_errors).find((e) => FRIENDLY.includes(e.kind))
  if (byKind) return byKind.kind
  const log = m.compile_log ?? ''
  if (log.includes("this bundle isn't cached")) return 'needs_download'
  if (log.includes('Running external tool biber')) return 'biber_unsupported'
  if (log.includes('accessing absolute path')) return 'outside_file'
  return log.trim() === '' && parseCompileErrors(m.compile_errors).length === 0 ? 'compile_timeout' : null
}
