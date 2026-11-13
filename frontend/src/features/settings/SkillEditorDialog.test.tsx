// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Skill } from '@/api/client'
import { SkillEditorDialog } from './SkillEditorDialog'

const mocks = vi.hoisted(() => ({ useCreateSkill: vi.fn(), useUpdateSkill: vi.fn() }))
vi.mock('@/api/queries', () => mocks)

function mutation(overrides: Record<string, unknown> = {}) {
  return { mutate: vi.fn(), isPending: false, error: null, reset: vi.fn(), ...overrides }
}

const custom: Skill = {
  id: 'custom:11111111-1111-1111-1111-111111111111',
  label: 'My check',
  description: 'Mine.',
  scope: 'workspace',
  instructions: 'Look at the sample.',
  version: 1,
  is_listed: true,
  is_paper_default: false,
  is_workspace_default: false,
  state: 'custom',
  lens: 'full',
}

let create: ReturnType<typeof mutation>
let update: ReturnType<typeof mutation>

beforeAll(() => {
  Element.prototype.hasPointerCapture = () => false
  Element.prototype.releasePointerCapture = () => {}
  Element.prototype.scrollIntoView = () => {}
})

beforeEach(() => {
  create = mutation()
  update = mutation()
  mocks.useCreateSkill.mockReturnValue(create)
  mocks.useUpdateSkill.mockReturnValue(update)
})

describe('SkillEditorDialog', () => {
  it('shows the fixed note that PaperLab handles citations and formatting', () => {
    render(<SkillEditorDialog open onOpenChange={vi.fn()} />)
    expect(
      screen.getByText(
        'PaperLab already tells the model to cite its sources and answer in plain prose, so a skill needn\'t say how to format or cite.',
      ),
    ).toBeInTheDocument()
  })

  it('creates a new skill with the typed fields', () => {
    render(<SkillEditorDialog open onOpenChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Quick look' } })
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'A short look.' } })
    fireEvent.change(screen.getByLabelText('Instructions'), { target: { value: 'Check the sample size.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(create.mutate).toHaveBeenCalledWith(
      { label: 'Quick look', description: 'A short look.', scope: 'both', instructions: 'Check the sample size.', lens: 'full' },
      expect.any(Object),
    )
    expect(update.mutate).not.toHaveBeenCalled()
  })

  it('sends only the fields that changed when editing', () => {
    render(<SkillEditorDialog open onOpenChange={vi.fn()} skill={custom} />)
    fireEvent.change(screen.getByLabelText('Instructions'), { target: { value: 'Look harder.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(update.mutate).toHaveBeenCalledWith({ id: custom.id, instructions: 'Look harder.' }, expect.any(Object))
  })

  it('shows skill_label_taken inside the dialog', () => {
    create = mutation({ error: new ApiError('Conflict', 409, { detail: 'skill_label_taken' }) })
    mocks.useCreateSkill.mockReturnValue(create)
    render(<SkillEditorDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByRole('dialog')).toHaveTextContent('Another skill already has this label')
  })

  it('refuses empty instructions without calling the API', () => {
    render(<SkillEditorDialog open onOpenChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Quick look' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('Write the instructions the model should follow.')
    expect(create.mutate).not.toHaveBeenCalled()
  })

  describe('lens', () => {
    const lensSelect = () => screen.getByRole('combobox', { name: 'Lens' })

    it('offers Whole paper, then the four lenses with their labels', () => {
      render(<SkillEditorDialog open onOpenChange={vi.fn()} />)
      fireEvent.pointerDown(lensSelect(), { button: 0, ctrlKey: false, pointerType: 'mouse' })
      expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
        'Whole paper',
        'Key ideas',
        'Critical check',
        'How they did it',
        'Related work',
      ])
    })

    it('starts a new skill on Whole paper and sends the lens picked', () => {
      render(<SkillEditorDialog open onOpenChange={vi.fn()} />)
      expect(lensSelect()).toHaveTextContent('Whole paper')
      fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Quick look' } })
      fireEvent.change(screen.getByLabelText('Instructions'), { target: { value: 'Check the sample size.' } })
      fireEvent.pointerDown(lensSelect(), { button: 0, ctrlKey: false, pointerType: 'mouse' })
      fireEvent.click(screen.getByRole('option', { name: 'Critical check' }))
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))
      expect(create.mutate).toHaveBeenCalledWith(expect.objectContaining({ lens: 'critical' }), expect.any(Object))
    })

    it('pre-selects a skill its lens when editing', () => {
      render(<SkillEditorDialog open onOpenChange={vi.fn()} skill={{ ...custom, lens: 'method' }} />)
      expect(lensSelect()).toHaveTextContent('How they did it')
    })

    it('sends only the lens when only the lens changed', () => {
      render(<SkillEditorDialog open onOpenChange={vi.fn()} skill={custom} />)
      fireEvent.pointerDown(lensSelect(), { button: 0, ctrlKey: false, pointerType: 'mouse' })
      fireEvent.click(screen.getByRole('option', { name: 'Key ideas' }))
      fireEvent.click(screen.getByRole('button', { name: 'Save' }))
      expect(update.mutate).toHaveBeenCalledWith({ id: custom.id, lens: 'key_ideas' }, expect.any(Object))
    })
  })
})
