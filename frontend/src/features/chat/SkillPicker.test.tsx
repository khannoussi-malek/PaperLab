// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import type { Skill } from '@/api/client'
import { SkillPicker } from './SkillPicker'

beforeAll(() => {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.releasePointerCapture = () => {}
  Element.prototype.scrollIntoView = () => {}
})

const skill = (id: string, label: string) => ({ id, label }) as Skill
const skills = [skill('builtin:limits', 'Limits'), skill('custom:mine', 'My method check')]

function open() {
  fireEvent.pointerDown(screen.getByRole('combobox', { name: 'Skill' }), { button: 0, ctrlKey: false, pointerType: 'mouse' })
  return screen.getAllByRole('option')
}

describe('SkillPicker', () => {
  it('lists No skill first, then the skills, then Manage skills…', () => {
    render(<SkillPicker skills={skills} value={null} onChange={vi.fn()} />)
    expect(open().map((option) => option.textContent)).toEqual(['No skill', 'Limits', 'My method check', 'Manage skills…'])
  })

  it('shows the picked skill on the trigger, or No skill', () => {
    const { rerender } = render(<SkillPicker skills={skills} value="custom:mine" onChange={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Skill' })).toHaveTextContent('My method check')
    rerender(<SkillPicker skills={skills} value={null} onChange={vi.fn()} />)
    expect(screen.getByRole('combobox', { name: 'Skill' })).toHaveTextContent('No skill')
  })

  it('reports a pick, and No skill as null', () => {
    const onChange = vi.fn()
    render(<SkillPicker skills={skills} value="builtin:limits" onChange={onChange} />)
    fireEvent.click(within(open()[0].closest('[role="listbox"]')! as HTMLElement).getByRole('option', { name: 'My method check' }))
    expect(onChange).toHaveBeenLastCalledWith('custom:mine')
    fireEvent.pointerDown(screen.getByRole('combobox', { name: 'Skill' }), { button: 0, ctrlKey: false, pointerType: 'mouse' })
    fireEvent.click(screen.getByRole('option', { name: 'No skill' }))
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('Manage skills… opens Settings on the skills section, not a pick', () => {
    const onChange = vi.fn()
    render(<SkillPicker skills={skills} value={null} onChange={onChange} />)
    open()
    fireEvent.click(screen.getByRole('option', { name: 'Manage skills…' }))
    expect(location.hash).toBe('#/settings/skills')
    expect(onChange).not.toHaveBeenCalled()
  })
})
