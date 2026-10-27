// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { InsertMenu } from './InsertMenu'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.scrollIntoView ??= () => {}

test('the Insert button opens a menu whose Table item opens the table dialog', async () => {
  vi.spyOn(api, 'listDatasets').mockResolvedValue([])
  render(
    <QueryClientProvider client={new QueryClient()}>
      <InsertMenu manuscriptId="m1" labelTexts={() => []} onInsert={async () => ({ ok: true })} />
    </QueryClientProvider>,
  )
  fireEvent.keyDown(screen.getByRole('button', { name: 'Insert' }), { key: 'Enter' })
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Table…' }))
  expect(await screen.findByRole('dialog', { name: 'Insert a table' })).toBeInTheDocument()
})

function open() {
  vi.spyOn(api, 'listDatasets').mockResolvedValue([])
  render(
    <QueryClientProvider client={new QueryClient()}>
      <section><div className="cm-content" tabIndex={0} data-testid="editor" />
        <InsertMenu manuscriptId="m1" labelTexts={() => []} onInsert={async () => ({ ok: true })} />
      </section>
    </QueryClientProvider>,
  )
  const button = screen.getByRole('button', { name: 'Insert' })
  button.focus()
  fireEvent.keyDown(button, { key: 'Enter' })
  return button
}

test('after a successful insert focus is in the editor', async () => {
  open()
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Table…' }))
  fireEvent.mouseDown(await screen.findByRole('tab', { name: 'Paste' }))
  fireEvent.change(screen.getByLabelText('Paste a table'), { target: { value: 'a,b\n1,2' } })
  const insert = screen.getAllByRole('button', { name: 'Insert' }).find((b) => b.closest('[role=dialog]'))!
  fireEvent.click(insert)
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId('editor')))
})

test('Esc returns focus to the Insert button', async () => {
  const button = open()
  fireEvent.click(await screen.findByRole('menuitem', { name: 'Table…' }))
  fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' })
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(document.activeElement).toBe(button))
})
