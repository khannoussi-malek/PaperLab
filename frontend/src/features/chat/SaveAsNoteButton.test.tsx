// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SaveAsNoteButton } from './SaveAsNoteButton'

describe('SaveAsNoteButton', () => {
  it('sends nothing while a save is pending, however often it is clicked', () => {
    const onSave = vi.fn()
    render(<SaveAsNoteButton canSave saving error={null} style={{}} onSave={onSave} />)
    const button = screen.getByRole('button', { name: /save as note/i })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(button).toBeDisabled()
    expect(onSave).not.toHaveBeenCalled()
  })
})
