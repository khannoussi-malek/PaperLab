import { describe, expect, it } from 'vitest'
import type { Check, Note } from '@/api/client'
import { checkProblem, exitTestLine, exitTestNote, exitTestStatus, streamedLine } from './exitTest'

const note = (fields: Partial<Note>): Note => ({ id: 'n', kind: 'summary', provenance: 'human', created_at: '2026-10-01T00:00:00Z', ...fields }) as Note
const check = (fields: Partial<Check>): Check =>
  ({ note_id: 'n', stale: false, created_at: '2026-10-05T12:00:00Z', lines: [], ...fields }) as Check

describe('exitTestNote', () => {
  it('takes the newest human note of the kind and ignores AI notes and other kinds', () => {
    const notes = [
      note({ id: 'old', created_at: '2026-10-01T00:00:00Z' }),
      note({ id: 'new', created_at: '2026-10-03T00:00:00Z' }),
      note({ id: 'ai', provenance: 'llm', created_at: '2026-10-09T00:00:00Z' }),
      note({ id: 'edited', provenance: 'llm_edited', created_at: '2026-10-09T00:00:00Z' }),
      note({ id: 'other', kind: 'five_cs', created_at: '2026-10-09T00:00:00Z' }),
    ]
    expect(exitTestNote(notes, 'summary')?.id).toBe('new')
    expect(exitTestNote(notes, 'reconstruction')).toBeUndefined()
  })
})

describe('exitTestStatus', () => {
  it('is not_written without a note, not_checked without a check', () => {
    expect(exitTestStatus(undefined, undefined)).toBe('not_written')
    expect(exitTestStatus(note({}), undefined)).toBe('not_checked')
  })
  it('is stale when the check says so, even with lines', () => {
    expect(exitTestStatus(note({}), check({ stale: true, lines: [{ verdict: 'missing', text: 'x' }] }))).toBe('stale')
  })
  it('counts missing and unsupported lines, and carries the date', () => {
    const lines = [
      { verdict: 'missing', text: 'a' }, { verdict: 'missing', text: 'b' },
      { verdict: 'unsupported', text: 'c' }, { verdict: 'supported', text: 'd' },
    ] as Check['lines']
    expect(exitTestStatus(note({}), check({ lines }))).toEqual({ missing: 2, unsupported: 1, at: '2026-10-05T12:00:00Z' })
  })
})

describe('exitTestLine', () => {
  const at = '2026-10-05T12:00:00Z'
  const date = new Date(at).toLocaleDateString(undefined, { dateStyle: 'medium' })
  it('words the four states with their actions', () => {
    expect(exitTestLine('five_cs', 'not_written')).toEqual({ text: 'Your five Cs: not written yet', action: 'write' })
    expect(exitTestLine('summary', 'not_checked')).toEqual({ text: 'Your summary: not checked yet', action: 'open' })
    expect(exitTestLine('reconstruction', 'stale')).toEqual({ text: 'Your reconstruction: changed since its check', action: 'open' })
    expect(exitTestLine('summary', { missing: 2, unsupported: 1, at })).toEqual({
      text: `Your summary: checked ${date}: 2 missing, 1 unsupported`,
      action: 'open',
    })
  })
})

describe('streamedLine', () => {
  it('reads each verdict with its text', () => {
    expect(streamedLine('Missing: the dataset [C2]\n')).toEqual({ verdict: 'missing', text: 'the dataset [C2]' })
    expect(streamedLine('Unsupported: a claim [C1]\n')).toEqual({ verdict: 'unsupported', text: 'a claim [C1]' })
    expect(streamedLine('Supported: the loss [C3]\n')).toEqual({ verdict: 'supported', text: 'the loss [C3]' })
  })
  it('is null on junk', () => {
    expect(streamedLine('Here is my answer\n')).toBeNull()
    expect(streamedLine('')).toBeNull()
    expect(streamedLine('Missing:\n')).toBeNull()
  })
})

describe('checkProblem', () => {
  const plain = (message: string, extra = {}) => ({ message, retryable: false, reindex: false, ...extra })
  it('words the check codes', () => {
    expect(checkProblem(409, 'not_your_text', 'summary')).toEqual(plain('Only text you wrote can be checked. This note came from AI.'))
    expect(checkProblem(422, 'not_checkable', 'summary')).toEqual(plain('Only a Five Cs, Summary or Reconstruction note can be checked.'))
    expect(checkProblem(422, 'nothing_written', 'summary')).toEqual(plain('Write your answers first: this note has only its headings.'))
    expect(checkProblem(422, 'note_too_long', 'summary')).toEqual(plain('A check reads up to 8,000 characters. Shorten the note first.'))
    expect(checkProblem(409, 'note_not_on_one_paper', 'summary')).toEqual(plain('A check reads one paper. Link this note to exactly one paper.'))
    expect(checkProblem(409, 'needs_full_text', 'summary')).toEqual(plain("A check reads the paper's sections. Attach its PDF first."))
    expect(checkProblem(409, 'no_model', 'summary')).toEqual(plain('Add a model in Settings to check your notes.', { settings: true }))
  })
  it('names How they did it for a reconstruction, else the sections', () => {
    expect(checkProblem(409, 'lens_empty', 'reconstruction')).toEqual(
      plain("This paper has no sections for How they did it, so a reconstruction can't be checked. Fix a section's role in the Lens tab."),
    )
    expect(checkProblem(409, 'lens_empty', 'summary')).toEqual(plain('This paper has no sections to check against.'))
  })
  it("leaves the rest to chat's refusal", () => {
    expect(checkProblem(409, 'paper_not_indexed', 'summary')).toMatchObject({ reindex: true })
    expect(checkProblem(500, 'boom', 'summary')).toMatchObject({ message: 'boom', retryable: true })
  })
})
