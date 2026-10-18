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
      <ExportSelectedMenu workspaceId="w1" paperIds={['p1', 'p2']} />
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
  expect(spy).toHaveBeenCalledWith(['p1', 'p2'], 'bibtex', 'w1')
})

test('RIS asks for ris, and a refusal is shown', async () => {
  const spy = vi.spyOn(api, 'exportSelection').mockRejectedValue(new Error('too_many_papers'))
  open()
  fireEvent.click(await screen.findByRole('menuitem', { name: 'RIS' }))
  expect((await screen.findByRole('alert')).textContent).toContain('1000 papers')
  expect(spy).toHaveBeenCalledWith(['p1', 'p2'], 'ris', 'w1')
})

test('the request body carries the workspace id', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response('x', { headers: { 'Content-Disposition': 'attachment; filename="citations.ris"' } }),
  )
  await api.exportSelection(['p1'], 'ris', 'w1')
  expect(JSON.parse(fetchSpy.mock.calls[0][1]!.body as string)).toEqual({ paper_ids: ['p1'], format: 'ris', workspace_id: 'w1' })
})
