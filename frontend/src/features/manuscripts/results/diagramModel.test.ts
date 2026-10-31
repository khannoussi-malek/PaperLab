import { describe, expect, it } from 'vitest'
import { ApiError, type Diagram } from '@/api/client'
import { AI_COMMENT, canInsert, diagramBlock, diagramLabel, diagramPackages, diagramProblem, diagramStartError, editableCode } from './diagramModel'

const row = (o: Partial<Diagram> = {}): Diagram => ({
  id: 'd1', description: 'A pipeline', status: 'done', code: '\\begin{tikzpicture}\\end{tikzpicture}', libraries: [], compiled: true,
  errors: [], labels_not_in_description: [], reason: null, model: 'm', ai: true, created_at: 't0', updated_at: 't1', ...o,
})

describe('diagramBlock', () => {
  it('puts the AI comment first, an empty caption, and the label last', () => {
    expect(AI_COMMENT).toBe('% diagram drawn by PaperLab AI from your description')
    expect(diagramBlock('PIC', 'fig:diagram-x')).toBe(
      '% diagram drawn by PaperLab AI from your description\n\\begin{figure}[t]\n\\centering\nPIC\n\\caption{}\n\\label{fig:diagram-x}\n\\end{figure}',
    )
  })

  it('asks for tikz and each library as a pseudo-package', () => {
    expect(diagramPackages([])).toEqual(['tikz'])
    expect(diagramPackages(['arrows.meta', 'positioning'])).toEqual(['tikz', 'tikzlibrary:arrows.meta', 'tikzlibrary:positioning'])
  })
})

describe('diagramLabel', () => {
  it('slugs the first four words, and gives -2 when any file already has it', () => {
    const d = 'A pipeline: "Raw data" → "Cleaning" → "Model"'
    expect(diagramLabel([], d)).toBe('fig:diagram-a-pipeline-raw-data')
    expect(diagramLabel(['x', '\\label{fig:diagram-a-pipeline-raw-data}'], d)).toBe('fig:diagram-a-pipeline-raw-data-2')
  })
})

describe('canInsert', () => {
  it.each([
    [{}, true],
    [{ status: 'running' as const }, false],
    [{ status: 'queued' as const }, false],
    [{ status: 'failed' as const }, false],
    [{ status: 'interrupted' as const, code: null }, false],
    [{ compiled: false }, false],
    [{ compiled: null }, false],
    [{ errors: [{ line: 2, message: 'Undefined control sequence.' }] }, false],
    [{ code: null }, false],
  ])('%o → %s', (o, ok) => expect(canInsert(row(o))).toBe(ok))
})

describe('plain words', () => {
  it('names each reason the backend gives', () => {
    expect(diagramProblem(row({ compiled: false, reason: 'compile_timeout' }))).toBe('The diagram took too long to draw.')
    expect(diagramProblem(row({ status: 'failed', code: null, reason: 'model_error' }))).toBe("The model didn't give a usable answer. Try again or describe it differently.")
    expect(diagramProblem(row({ status: 'interrupted', code: null }))).toBe('The diagram stopped before it finished. Try again.')
    expect(diagramProblem(row({ compiled: false, reason: 'some_new_code' }))).toBe("The diagram didn't compile.")
    expect(diagramProblem(row())).toBeNull()
  })

  it.each([
    ['outside_file', "The diagram tried to read a file, which PaperLab doesn't allow."],
    ['compile_failed', "PaperLab couldn't draw the preview. Try Update preview again."],
    ['check_failed', 'Something went wrong while drawing. Try again.'],
    ['no_model', 'Add a model in Settings to draw diagrams.'],
    ['diagram_invalid', "The diagram code isn't allowed as written; see the problems listed."],
    ['queue_unavailable', "PaperLab's background worker isn't running. Try again in a moment."],
    ['remote_model_needs_confirm', 'The default model is now a cloud model. Start again to confirm sending your text.'],
    ['library_not_cached', 'Something went wrong drawing the diagram. Try again.'], // never sent by the backend: the generic words
  ])('a failed run with %s says so in the backend\'s words', (reason, words) => {
    expect(diagramProblem(row({ status: 'failed', code: null, reason }))).toBe(words)
  })

  it('maps start refusals; the remote question is not an error', () => {
    expect(diagramStartError(new ApiError('no_model', 409, { detail: 'no_model' }))).toBe('Add a model in Settings to draw a diagram.')
    expect(diagramStartError(new ApiError('diagram_running', 409, { detail: 'diagram_running' }))).toBe('A diagram is already being drawn. Wait for it or cancel it.')
    expect(diagramStartError(new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', host: 'h' }))).toBeNull()
  })

  it('shows the libraries as \\usetikzlibrary lines above the picture, so an edit keeps them', () => {
    expect(editableCode(row({ code: 'PIC', libraries: ['arrows.meta', 'positioning'] }))).toBe('\\usetikzlibrary{arrows.meta,positioning}\nPIC')
    expect(editableCode(row({ code: 'PIC' }))).toBe('PIC')
  })
})
