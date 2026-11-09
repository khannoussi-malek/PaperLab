// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { Breadcrumb } from './Breadcrumb'
import { primaryPath } from './navPath'
import { prov } from './fixture'

test('shows the search, the papers and how each step was reached', () => {
  render(<Breadcrumb path={primaryPath(prov, 'C')} data={prov} onGo={() => {}} />)
  expect(screen.getByRole('button', { name: /graph search/ })).toBeInTheDocument()
  expect(screen.getByText('it cites')).toBeInTheDocument()
  expect(screen.getByText('cited by')).toBeInTheDocument()
})

test('clicking an entry calls onGo with its index', () => {
  const onGo = vi.fn()
  render(<Breadcrumb path={primaryPath(prov, 'C')} data={prov} onGo={onGo} />)
  fireEvent.click(screen.getByRole('button', { name: 'Paper B' }))
  expect(onGo).toHaveBeenCalledWith(2)
})

test('a long path shows first, … and the last two; the menu lists the hidden ones', async () => {
  const onGo = vi.fn()
  render(<Breadcrumb path={primaryPath(prov, 'F')} data={prov} onGo={onGo} />)
  expect(screen.queryByRole('button', { name: 'Paper B' })).toBeNull()
  fireEvent.keyDown(screen.getByRole('button', { name: '…' }), { key: 'Enter' })
  const items = await screen.findAllByRole('menuitem')
  expect(items.map((i) => i.textContent)).toEqual(['Paper A', 'Paper B', 'Paper C', 'Paper D'])
  fireEvent.click(screen.getByRole('menuitem', { name: 'Paper B' }))
  expect(onGo).toHaveBeenCalledWith(2)
})
