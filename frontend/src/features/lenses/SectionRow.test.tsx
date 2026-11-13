// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Role, Section } from '@/api/client'
import { SectionRow } from './SectionRow'

const section = (over: Partial<Section> = {}): Section =>
  ({ title: '2 Method', role: 'method', source: 'auto', page: 2, preview: 'We train.', first_chunk_id: 'c2', chunk_ids: ['c2'], ...over }) as Section

const row = (s: Section, onJump = vi.fn()) => (
  <ul>
    <SectionRow section={s} busy={false} onJump={onJump} onRoleChange={() => {}} />
  </ul>
)
const disclosure = () => screen.getByRole('button', { name: 'What to look for' })
const METHOD_QUESTION = 'Could you repeat what they did from this description alone?'
const RESULTS_QUESTION = 'Do the results answer the question the introduction asked?'

describe('SectionRow reader checklist', () => {
  it('is closed by default', () => {
    render(row(section()))
    expect(disclosure()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(METHOD_QUESTION)).toBeNull()
  })

  it('opening it lists the questions for a method section', () => {
    render(row(section()))
    fireEvent.click(disclosure())
    expect(disclosure()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(METHOD_QUESTION)).toBeInTheDocument()
  })

  it.each(['back', 'other'] as Role[])('a %s section has no disclosure', (role) => {
    render(row(section({ role })))
    expect(screen.queryByRole('button', { name: 'What to look for' })).toBeNull()
  })

  it("follows the section's role when the role changes", () => {
    const { rerender } = render(row(section()))
    fireEvent.click(disclosure())
    rerender(row(section({ role: 'results' })))
    expect(screen.getByText(RESULTS_QUESTION)).toBeInTheDocument()
    expect(screen.queryByText(METHOD_QUESTION)).toBeNull()
  })

  it('a click on the disclosure does not jump to the section', () => {
    const onJump = vi.fn()
    render(row(section(), onJump))
    fireEvent.click(disclosure())
    expect(onJump).not.toHaveBeenCalled()
  })
})

describe('SectionRow number suggestions (D33)', () => {
  it('the section menu offers Suggest numbers when the panel can', async () => {
    const onSuggestNumbers = vi.fn()
    render(
      <ul>
        <SectionRow section={section()} busy={false} onJump={() => {}} onRoleChange={() => {}} onSuggestNumbers={onSuggestNumbers} />
      </ul>,
    )
    fireEvent.pointerDown(screen.getByRole('button', { name: /Section actions/ }), { button: 0, ctrlKey: false })
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Suggest numbers…' }))
    expect(onSuggestNumbers).toHaveBeenCalled()
  })
})
