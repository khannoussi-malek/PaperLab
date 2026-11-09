// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, type Hit, type ProvNode } from '@/api/client'
import { AskPanel } from './AskPanel'

const node = (id: string, extra: object = {}) => ({ id, title: `Paper ${id}`, level: 0, snowballed: [], paths: 1, ...extra }) as unknown as ProvNode
const hit = (id: string, over: object = {}) => ({ id, title: `Paper ${id}`, paper_id: null, acquisition_status: 'candidate', ...over }) as unknown as Hit

let fetchSpy: ReturnType<typeof vi.spyOn>
beforeEach(() => {
  vi.spyOn(api, 'getSearchHit').mockImplementation(async (_w, id) => hit(id, id === 'B' ? { paper_id: 'p1', acquisition_status: 'imported' } : {}))
  vi.spyOn(api, 'listChat').mockResolvedValue([])
  vi.spyOn(api, 'listChatModels').mockResolvedValue([{ id: 'm1', name: 'fake', connection_name: 'c', is_default: true }] as never)
  vi.spyOn(api, 'listWorkspacePapers').mockResolvedValue([{ id: 'p9', title: 'Lib', has_pdf: true }] as never)
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('offline'))
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

function mount(n: ProvNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (x: ProvNode) => <QueryClientProvider client={client}><AskPanel workspaceId="w1" node={x} /></QueryClientProvider>
  const view = render(ui(n))
  return { show: (x: ProvNode) => view.rerender(ui(x)) }
}

test('a hit without a paper reads the abstract only', async () => {
  mount(node('A'))
  expect(await screen.findByText('Reads: Paper A (abstract only)')).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'Ask the AI' })).toBeTruthy()
})

test('a hit with a library file reads the full text', async () => {
  mount(node('B'))
  expect(await screen.findByText('Reads: Paper B (full text)')).toBeTruthy()
})

test('questions about a hit post to the hit chat URL', async () => {
  mount(node('A'))
  const box = await screen.findByLabelText('Question')
  await waitFor(() => expect((box as HTMLTextAreaElement).disabled).toBe(false))
  fireEvent.change(box, { target: { value: 'What is new?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
  await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
  expect(fetchSpy.mock.calls[0][0]).toBe('/api/workspaces/w1/search/hits/A/chat')
})

test('a library paper uses the paper chat and its file', async () => {
  const listChat = vi.spyOn(api, 'listChat')
  mount(node('paper:p9', { paper_id: 'p9' }))
  expect(await screen.findByText('Reads: Lib (full text)')).toBeTruthy()
  await waitFor(() => expect(listChat).toHaveBeenCalledWith({ kind: 'paper', id: 'p9' }))
})

test('stepping to another paper switches the chat to it', async () => {
  const listChat = vi.spyOn(api, 'listChat')
  const { show } = mount(node('A'))
  await waitFor(() => expect(listChat).toHaveBeenCalledWith({ kind: 'hit', workspaceId: 'w1', id: 'A' }))
  show(node('C'))
  await waitFor(() => expect(listChat).toHaveBeenCalledWith({ kind: 'hit', workspaceId: 'w1', id: 'C' }))
})

test('the panel folds and unfolds', async () => {
  mount(node('A'))
  fireEvent.click(await screen.findByRole('button', { name: 'Fold Ask the AI' }))
  expect(screen.queryByLabelText('Question')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Ask the AI' }))
  expect(await screen.findByLabelText('Question')).toBeTruthy()
})

test('the Reads line follows what the first stream event says the AI read', async () => {
  fetchSpy.mockResolvedValue(new Response('event: meta\ndata: {"source":"full_text"}\n\n', { headers: { 'content-type': 'text/event-stream' } }))
  mount(node('A'))
  expect(await screen.findByText('Reads: Paper A (abstract only)')).toBeTruthy()
  const box = await screen.findByLabelText('Question')
  await waitFor(() => expect((box as HTMLTextAreaElement).disabled).toBe(false))
  fireEvent.change(box, { target: { value: 'What is new?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
  expect(await screen.findByText('Reads: Paper A (full text)')).toBeTruthy()
})

test('below 900px the drawer takes focus when opened and Escape closes it', async () => {
  vi.stubGlobal('matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
  try {
    mount(node('A'))
    fireEvent.click(screen.getByRole('button', { name: 'Ask the AI' }))
    const drawer = await screen.findByRole('complementary', { name: 'Ask the AI' })
    await waitFor(() => expect(document.activeElement).toBe(drawer))
    fireEvent.keyDown(drawer, { key: 'Escape' })
    expect(screen.queryByRole('complementary', { name: 'Ask the AI' })).toBeNull()
  } finally {
    vi.unstubAllGlobals()
  }
})
