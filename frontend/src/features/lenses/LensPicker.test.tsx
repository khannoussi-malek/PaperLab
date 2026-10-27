// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import type { Lens } from '@/api/client'
import { LensPicker } from './LensPicker'
import type { LensReader } from './useLensReader'

const lens = (over: Partial<Lens>): Lens =>
  ({ id: 'related', label: 'Related work', chunk_ids: [], positional_fallback: false, missing_roles: [], ...over }) as Lens

const picker = (picked: Lens, headed = true) => {
  const reader = { lensId: picked.id, lens: picked, lenses: [picked], runCount: 0, runIndex: 0, headed } as unknown as LensReader
  render(<LensPicker reader={reader} />)
}

it('says why an empty lens shows nothing, next to the picker', () => {
  picker(lens({}))
  expect(document.querySelector('.lens-empty')).toHaveTextContent(
    "This paper has no sections for Related work. Switch to Full paper to fix a section's role.",
  )
  expect(document.querySelector('.lens-empty')).toHaveAttribute('aria-live', 'polite')
})

it('drops the role-fix hint for a paper with no headings', () => {
  picker(lens({}), false)
  expect(document.querySelector('.lens-empty')).toHaveTextContent(/^This paper has no sections for Related work\.$/)
})

it('says nothing for a lens with sections or for Full paper', () => {
  picker(lens({ chunk_ids: ['c1'] }))
  expect(document.querySelector('.lens-empty')).toHaveTextContent(/^$/)
  expect(screen.queryByText(/no sections/)).toBeNull()
})
