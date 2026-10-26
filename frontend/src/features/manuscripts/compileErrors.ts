export type CompileError = { file: string; line: number | null; message: string; kind: string }

const isCompileError = (e: unknown): e is CompileError =>
  typeof e === 'object' && e !== null && typeof (e as CompileError).file === 'string' && typeof (e as CompileError).message === 'string'

export const parseCompileErrors = (errors: readonly unknown[] | null | undefined): CompileError[] =>
  (errors ?? []).filter(isCompileError)

/** The messages that point at a line of `file`, for the editor's gutter. */
export const errorsFor = (errors: readonly unknown[] | null | undefined, file: string) =>
  parseCompileErrors(errors).flatMap((e) => (e.file === file && typeof e.line === 'number' ? [{ line: e.line, message: e.message }] : []))
