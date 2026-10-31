/** A diagram drawn from the researcher's own description: the block it inserts and its states in plain words (D118). */
import { ApiError, type Diagram } from '@/api/client'
import { remoteHost } from '../review/reviewModel'
import { slug, TIKZ_LIBRARY, uniqueLabel } from './insertBlock'

export const AI_COMMENT = '% diagram drawn by PaperLab AI from your description'

/** The figure that goes in on Insert: the AI comment on its own line first, an empty caption, the label last. */
export const diagramBlock = (picture: string, label: string): string =>
  `${AI_COMMENT}\n\\begin{figure}[t]\n\\centering\n${picture}\n\\caption{}\n\\label{${label}}\n\\end{figure}`

export const diagramPackages = (libraries: string[]): string[] => ['tikz', ...libraries.map((l) => `${TIKZ_LIBRARY}${l}`)]

/** `fig:diagram-<first four words>`, numbered against every `\label` in the texts. */
export const diagramLabel = (texts: string[], description: string): string =>
  uniqueLabel(texts, `fig:diagram-${slug(description.trim().split(/\s+/).slice(0, 4).join(' '))}`)

export const isLive = (d: Pick<Diagram, 'status'>): boolean => d.status === 'queued' || d.status === 'running'

export const canInsert = (d: Diagram): boolean => d.status === 'done' && d.compiled === true && d.errors.length === 0 && d.code !== null

/** What the LaTeX tab shows: the libraries as `\usetikzlibrary` above the picture, so an edit sent back keeps them. */
export const editableCode = (d: Pick<Diagram, 'code' | 'libraries'>): string =>
  `${d.libraries.length ? `\\usetikzlibrary{${d.libraries.join(',')}}\n` : ''}${d.code ?? ''}`

export const DIAGRAM_ERRORS: Record<string, string> = {
  compile_timeout: 'The diagram took too long to draw.',
  package_missing: "The diagram needs a LaTeX package PaperLab doesn't include offline.",
  library_not_cached: "The diagram uses a TikZ library PaperLab doesn't include offline.",
  model_error: "The model didn't give a usable answer. Try again or describe it differently.",
  model_unavailable: "The model isn't answering. Check it in Settings and try again.",
  diagram_too_large: 'The diagram is too large to preview. Try a simpler one.',
  cancelled: 'Stopped.',
  queue_unavailable: "PaperLab couldn't start drawing. Try again in a moment.",
}
const INTERRUPTED = 'The diagram stopped before it finished. Try again.'
const DIDNT_COMPILE = "The diagram didn't compile."
const FAILED = 'Something went wrong drawing the diagram. Try again.'

/** Why a finished run can't be inserted, in plain words; null while live or when it compiled. */
export function diagramProblem(d: Diagram): string | null {
  if (d.status === 'interrupted') return INTERRUPTED
  if (d.status === 'failed') return DIAGRAM_ERRORS[d.reason ?? ''] ?? FAILED
  if (d.status === 'done' && d.compiled !== true) return DIAGRAM_ERRORS[d.reason ?? ''] ?? DIDNT_COMPILE
  return null
}

const START_ERRORS: Record<string, string> = {
  no_model: 'Add a model in Settings to draw a diagram.',
  diagram_running: 'A diagram is already being drawn. Wait for it or cancel it.',
  description_invalid: 'Describe the diagram in up to 2,000 characters.',
}

/** A refused start or edit in plain words; null for the remote-model question, which is asked, not shown. */
export function diagramStartError(e: unknown): string | null {
  if (remoteHost(e)) return null
  if (e instanceof ApiError && START_ERRORS[e.code]) return START_ERRORS[e.code]
  return e instanceof Error ? e.message : 'Something went wrong. Please try again.'
}
