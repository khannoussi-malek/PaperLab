// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ScreeningAssist } from './ScreeningAssist'

// No shared renderWithClient helper exists yet — copied from SearchTab.test.tsx's own wrapper.
function renderWithClient(ui: React.ReactElement, client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
}

const state = (over = {}) => ({
  criteria: 'RCTs on sleep', ranked_used: false, suggest_status: 'idle', suggest_done: 0, suggest_total: 0,
  suggest_error: null, model_label: 'Ollama · qwen3:8b', model_is_local: true, model_host: 'localhost', ...over,
})

function stubFetch(routes: Record<string, (init?: RequestInit) => unknown>) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${new URL(url, 'http://x').pathname}`
    const body = routes[key]?.(init)
    return new Response(JSON.stringify(body ?? {}), { status: body === undefined ? 404 : 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())
const base = '/api/workspaces/w1/search'

describe('ScreeningAssist', () => {
  it('saves the criteria', async () => {
    const fetchMock = stubFetch({ [`GET ${base}/screening`]: () => state({ criteria: null }), [`PUT ${base}/screening`]: () => state() })
    renderWithClient(<ScreeningAssist workspaceId="w1" />)
    fireEvent.change(await screen.findByLabelText('Inclusion / exclusion criteria'), { target: { value: 'RCTs on sleep' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save criteria' }))
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(`${base}/screening`, expect.objectContaining({ method: 'PUT' })),
    )
  })

  it('starts suggestions without asking for a local model', async () => {
    const confirm = vi.spyOn(window, 'confirm')
    const fetchMock = stubFetch({ [`GET ${base}/screening`]: () => state(), [`POST ${base}/suggestions`]: () => state({ suggest_status: 'running' }) })
    renderWithClient(<ScreeningAssist workspaceId="w1" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest for unscreened hits' }))
    expect(confirm).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(`${base}/suggestions`, expect.objectContaining({ body: '{"confirm_remote":false}' })),
    )
  })

  it('asks before sending abstracts to a cloud model', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const fetchMock = stubFetch({ [`GET ${base}/screening`]: () => state({ model_is_local: false, model_host: 'api.openai.com' }) })
    renderWithClient(<ScreeningAssist workspaceId="w1" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Suggest for unscreened hits' }))
    expect(confirm).toHaveBeenCalledWith('Abstracts will be sent to api.openai.com and may cost money. Continue?')
    expect(fetchMock).not.toHaveBeenCalledWith(`${base}/suggestions`, expect.anything())
  })

  it('shows progress and a Stop button while running', async () => {
    stubFetch({ [`GET ${base}/screening`]: () => state({ suggest_status: 'running', suggest_done: 140, suggest_total: 2710 }) })
    renderWithClient(<ScreeningAssist workspaceId="w1" />)
    expect(await screen.findByText('Suggesting… 140 / 2710')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument()
  })

  it('disables Suggest when no chat model', async () => {
    stubFetch({ [`GET ${base}/screening`]: () => state({ model_label: null, model_is_local: null, model_host: null }) })
    renderWithClient(<ScreeningAssist workspaceId="w1" />)
    expect(await screen.findByRole('button', { name: 'Suggest for unscreened hits' })).toBeDisabled()
    expect(screen.getByText('Set up a chat model in Settings to get suggestions.')).toBeInTheDocument()
  })

  it('disables Suggest until criteria are saved, and shows the last error', async () => {
    stubFetch({ [`GET ${base}/screening`]: () => state({ criteria: null, suggest_error: "Can't reach localhost:11434" }) })
    renderWithClient(<ScreeningAssist workspaceId="w1" />)
    expect(await screen.findByRole('button', { name: 'Suggest for unscreened hits' })).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent("Can't reach localhost:11434")
  })
})
