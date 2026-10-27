// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
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
