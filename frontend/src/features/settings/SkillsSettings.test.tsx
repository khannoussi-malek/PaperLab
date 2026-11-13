// @vitest-environment jsdom
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Skill } from '@/api/client'
import { SkillsSettings } from './SkillsSettings'

const mocks = vi.hoisted(() => ({
  useSkills: vi.fn(),
  useCreateSkill: vi.fn(),
  useUpdateSkill: vi.fn(),
  useDeleteSkill: vi.fn(),
  useResetSkill: vi.fn(),
  useSetSkillDefault: vi.fn(),
}))
vi.mock('@/api/queries', () => mocks)

function mutation(overrides: Record<string, unknown> = {}) {
  return { mutate: vi.fn(), isPending: false, error: null, reset: vi.fn(), ...overrides }
}

const base = (overrides: Partial<Skill>): Skill => ({
  id: 'builtin:check-evaluation',
  label: 'Check the evaluation',
  description: 'Looks at how the paper tested its claims.',
  scope: 'paper',
  instructions: 'Read the method first.',
  lens: 'full',
  version: 1,
  is_listed: true,
  is_paper_default: false,
  is_workspace_default: false,
  state: 'builtin',
  ...overrides,
})

const CHECK = base({})
const EDITED_BOTH = base({ id: 'builtin:study-type', label: 'Study type', scope: 'both', state: 'edited', is_paper_default: true })
const MINE = base({ id: 'custom:22222222-2222-2222-2222-222222222222', label: 'My ws check', scope: 'workspace', state: 'custom' })
const HIDDEN = base({ id: 'builtin:plain-explanation', label: 'Plain explanation', scope: 'both', is_listed: false })
const COPY = base({ id: 'custom:33333333-3333-3333-3333-333333333333', label: 'Check the evaluation (copy)', state: 'custom' })

let skillsByKind: Record<'paper' | 'workspace', Skill[]>
let mut: Record<string, ReturnType<typeof mutation>>

beforeEach(() => {
  skillsByKind = {
    paper: [CHECK, EDITED_BOTH, HIDDEN, COPY],
    workspace: [EDITED_BOTH, MINE, HIDDEN, COPY],
  }
  mut = {
    create: mutation(),
    update: mutation(),
    remove: mutation(),
    reset: mutation(),
    setDefault: mutation(),
  }
  mocks.useSkills.mockImplementation((kind: 'paper' | 'workspace') => ({
    data: skillsByKind[kind],
    isError: false,
    error: null,
    failureCount: 0,
    refetch: vi.fn(),
  }))
  mocks.useCreateSkill.mockReturnValue(mut.create)
  mocks.useUpdateSkill.mockReturnValue(mut.update)
  mocks.useDeleteSkill.mockReturnValue(mut.remove)
  mocks.useResetSkill.mockReturnValue(mut.reset)
  mocks.useSetSkillDefault.mockReturnValue(mut.setDefault)
})

/** The row (article) for the skill with this label. */
function rowFor(label: string) {
  return screen.getByRole('heading', { name: label }).closest('article') as HTMLElement
}

describe('SkillsSettings rows', () => {
  it('shows each skill once with its scope, state and default markers', () => {
    render(<SkillsSettings />)
    expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(5)
    const study = within(rowFor('Study type'))
    expect(study.getByText('Both')).toBeInTheDocument()
    expect(study.getByText('Edited')).toBeInTheDocument()
    expect(study.getByText('Paper default')).toBeInTheDocument()
    expect(within(rowFor('My ws check')).getByText('Custom')).toBeInTheDocument()
    expect(within(rowFor('Check the evaluation')).getByText('Built-in')).toBeInTheDocument()
  })

  it('marks a hidden skill with a Hidden badge and offers Show', () => {
    render(<SkillsSettings />)
    const row = within(rowFor('Plain explanation'))
    expect(row.getByText('Hidden')).toBeInTheDocument()
    expect(row.getByRole('button', { name: 'Show' })).toBeInTheDocument()
    expect(row.queryByRole('button', { name: 'Hide' })).not.toBeInTheDocument()
  })

  it('offers default actions only for the chat kinds the scope allows', () => {
    render(<SkillsSettings />)
    const paperOnly = within(rowFor('Check the evaluation'))
    expect(paperOnly.getByRole('button', { name: 'Set as paper default' })).toBeInTheDocument()
    expect(paperOnly.queryByRole('button', { name: 'Set as workspace default' })).not.toBeInTheDocument()
    const workspaceOnly = within(rowFor('My ws check'))
    expect(workspaceOnly.getByRole('button', { name: 'Set as workspace default' })).toBeInTheDocument()
    expect(workspaceOnly.queryByRole('button', { name: 'Set as paper default' })).not.toBeInTheDocument()
    const both = within(rowFor('Study type'))
    expect(both.getByRole('button', { name: 'Remove paper default' })).toBeInTheDocument()
    expect(both.getByRole('button', { name: 'Set as workspace default' })).toBeInTheDocument()
  })

  it('offers Reset only for edited skills and Delete only for custom ones', () => {
    render(<SkillsSettings />)
    expect(within(rowFor('Study type')).getByRole('button', { name: 'Reset' })).toBeInTheDocument()
    expect(within(rowFor('Check the evaluation')).queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()
    expect(within(rowFor('Check the evaluation')).queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
    expect(within(rowFor('My ws check')).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(within(rowFor('My ws check')).queryByRole('button', { name: 'Reset' })).not.toBeInTheDocument()
  })
})

describe('SkillsSettings actions', () => {
  it('duplicates a skill as a custom copy with its resolved text and a numbered label', () => {
    render(<SkillsSettings />)
    fireEvent.click(within(rowFor('Check the evaluation')).getByRole('button', { name: 'Duplicate' }))
    expect(mut.create.mutate).toHaveBeenCalledWith(
      {
        label: 'Check the evaluation (copy 2)',
        description: 'Looks at how the paper tested its claims.',
        scope: 'paper',
        instructions: 'Read the method first.',
  lens: 'full',
      },
    )
  })

  it('hides a skill and shows it again through an update', () => {
    render(<SkillsSettings />)
    fireEvent.click(within(rowFor('Check the evaluation')).getByRole('button', { name: 'Hide' }))
    expect(mut.update.mutate).toHaveBeenLastCalledWith({ id: CHECK.id, is_listed: false })
    fireEvent.click(within(rowFor('Plain explanation')).getByRole('button', { name: 'Show' }))
    expect(mut.update.mutate).toHaveBeenLastCalledWith({ id: HIDDEN.id, is_listed: true })
  })

  it('sets a paper default, and clears it when it is already the default', () => {
    render(<SkillsSettings />)
    fireEvent.click(within(rowFor('Check the evaluation')).getByRole('button', { name: 'Set as paper default' }))
    expect(mut.setDefault.mutate).toHaveBeenLastCalledWith({ id: CHECK.id, scope: 'paper', on: true })
    fireEvent.click(within(rowFor('Study type')).getByRole('button', { name: 'Remove paper default' }))
    expect(mut.setDefault.mutate).toHaveBeenLastCalledWith({ id: EDITED_BOTH.id, scope: 'paper', on: false })
  })

  it('resets an edited built-in skill', () => {
    render(<SkillsSettings />)
    fireEvent.click(within(rowFor('Study type')).getByRole('button', { name: 'Reset' }))
    expect(mut.reset.mutate).toHaveBeenCalledWith(EDITED_BOTH.id)
  })

  it('deletes a custom skill only after confirming in a dialog, never with window.confirm', () => {
    const confirm = vi.spyOn(window, 'confirm')
    render(<SkillsSettings />)
    fireEvent.click(within(rowFor('My ws check')).getByRole('button', { name: 'Delete' }))
    const dialog = screen.getByRole('dialog')
    expect(mut.remove.mutate).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    expect(mut.remove.mutate).toHaveBeenCalledWith(MINE.id, expect.any(Object))
    expect(confirm).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('opens a blank editor from New skill', () => {
    render(<SkillsSettings />)
    fireEvent.click(screen.getByRole('button', { name: 'New skill' }))
    expect(screen.getByRole('dialog')).toHaveTextContent('New skill')
    expect(screen.getByLabelText('Label')).toHaveValue('')
  })

  it('keeps the attribution line under the list', () => {
    render(<SkillsSettings />)
    expect(screen.getByText('Four skills draw on the community LLM reporting guidelines at llm-guidelines.org.')).toBeInTheDocument()
  })
})
