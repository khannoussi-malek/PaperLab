import { ApiError } from '@/api/client'

const GENERIC = 'Something went wrong. Please try again.'
type Details = Record<string, unknown>

const mb = (bytes: unknown) => (typeof bytes === 'number' ? `${Math.max(1, Math.round(bytes / (1024 * 1024)))} MB` : 'the limit')
const named = (path: unknown) => (typeof path === 'string' && path ? ` "${path}"` : '')

const MESSAGES: Record<string, (d: Details) => string> = {
  file_changed: () => 'This file changed somewhere else since you opened it.',
  file_exists: () => 'A file with that name already exists.',
  bad_path: (d) => `The file name${named(d.path)} isn't allowed. Use letters, numbers, dashes and slashes for folders.`,
  reserved_path: (d) => `The name${named(d.path)} is kept for PaperLab, so pick another.`,
  unsupported_file_type: () => "PaperLab can't hold that type of file yet.",
  file_too_large: (d) => `That file is bigger than ${mb(d.limit)}.`,
  manuscript_too_large: () => 'This manuscript is too big for PaperLab to hold.',
  too_many_files: () => 'This manuscript has more files than PaperLab can hold.',
  bad_zip: (d) => `That zip couldn't be read${named(d.path)}. Check it opens on your computer and try again.`,
  no_main_file: () => "PaperLab couldn't find a main .tex file in that zip.",
  not_text: (d) => `The file${named(d.path)} isn't plain text, so it can't be a .tex or .bib file.`,
  main_file_not_tex: () => 'The main file has to be a .tex file.',
  unknown_template: () => "That template isn't available.",
  package_missing: (d) =>
    `This project uses a LaTeX package PaperLab doesn't include yet${typeof d.name === 'string' && d.name ? `: ${d.name}` : ''}.`,
  compile_interrupted: () => 'The last compile was interrupted. Compile again.',
  main_file: () => "The main file can't be deleted. Make another file the main one first.",
  unknown_file: () => 'That file is no longer in this manuscript.',
  unknown_workspace: () => 'That workspace no longer exists.',
  biber_unsupported: () =>
    "This project uses biblatex with Biber, which PaperLab can't run yet. Switch to `backend=bibtex` or natbib.",
  compile_timeout: () => 'Compiling took longer than a minute and was stopped.',
  outside_file: () => 'This project tries to read or write a file outside itself, so PaperLab stopped the compile.',
  no_pdf: () => "There's no PDF yet. Compile the manuscript first.",
}

/** One warm, plain sentence for a manuscript API error code, using the details the server sent (path, limit). */
export function manuscriptErrorMessage(code: string, details: Details = {}): string {
  return MESSAGES[code]?.(details) ?? GENERIC
}

/** The sentence for any thrown error: a mapped server code gets its copy, anything else the server's own message. */
export function manuscriptFailure(error: Error): string {
  if (error instanceof ApiError && error.code in MESSAGES) return manuscriptErrorMessage(error.code, error.body)
  return error.message || GENERIC
}
