// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { ExportSelectedMenu } from './ExportSelectedMenu'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function open() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExportSelectedMenu paperIds={['p1', 'p2']} />
    </QueryClientProvider>,
  )
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Export selected…' }))
}

test('BibTeX posts the selected ids and downloads the returned file', async () => {
  const spy = vi.spyOn(api, 'exportSelection').mockResolvedValue({ blob: new Blob(['x']), filename: 'citations.bib' })
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  open()
  fireEvent.click(await screen.findByRole('menuitem', { name: 'BibTeX' }))
  await waitFor(() => expect(click).toHaveBeenCalled())
  expect(spy).toHaveBeenCalledWith(['p1', 'p2'], 'bibtex')
})

test('RIS asks for ris, and a refusal is shown', async () => {
  const spy = vi.spyOn(api, 'exportSelection').mockRejectedValue(new Error('too_many_papers'))
  open()
  fireEvent.click(await screen.findByRole('menuitem', { name: 'RIS' }))
  expect((await screen.findByRole('alert')).textContent).toContain('too_many_papers')
  expect(spy).toHaveBeenCalledWith(['p1', 'p2'], 'ris')
})
