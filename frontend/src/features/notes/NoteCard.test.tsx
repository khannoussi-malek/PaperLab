// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeAll, expect, test, vi } from 'vitest'
import { NoteCard } from './NoteCard'

beforeAll(() => {
  window.HTMLElement.prototype.hasPointerCapture ??= () => false
  window.HTMLElement.prototype.scrollIntoView ??= () => {}
})

const note = { id: 'a', body: 'text', kind: null, provenance: 'human', color: '#facc15', created_at: '2020-01-01T00:00:00Z', anchors: [], paper_ids: [], charts: [] } as never

function setup() {
  const onColorChange = vi.fn().mockResolvedValue(true)
  const onDelete = vi.fn().mockResolvedValue(undefined)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <NoteCard note={note} onUpdate={vi.fn()} onColorChange={onColorChange} onDelete={onDelete} />
    </QueryClientProvider>,
  )
  return { onColorChange, onDelete }
}

const open = () => fireEvent.pointerDown(screen.getByRole('button', { name: 'Note actions' }), { button: 0, ctrlKey: false })

test('a card at rest shows only Edit and the actions menu', () => {
  setup()
  expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-label') ?? b.textContent)).toEqual(['Edit', 'Note actions'])
})

test('the menu holds Attach chart, Papers, Colour and Delete; Delete calls onDelete', async () => {
  const { onDelete } = setup()
  open()
  for (const name of ['Attach chart', 'Papers', 'Colour', 'Delete']) expect(await screen.findByRole('menuitem', { name })).toBeTruthy()
  fireEvent.click(screen.getByRole('menuitem', { name: 'Delete' }))
  expect(onDelete).toHaveBeenCalled()
})

test('choosing a colour in the menu calls onColorChange', async () => {
  const { onColorChange } = setup()
  open()
  fireEvent.keyDown(await screen.findByRole('menuitem', { name: 'Colour' }), { key: 'ArrowRight' })
  fireEvent.click(await screen.findByRole('button', { name: 'Blue' }))
  expect(onColorChange).toHaveBeenCalledWith('#60a5fa')
})
