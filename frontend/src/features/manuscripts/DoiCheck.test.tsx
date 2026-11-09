// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type CheckFinding, type DoiCheckResult } from '@/api/client'
import { DoiCheck } from './DoiCheck'

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
const done = (over: Partial<DoiCheckResult> = {}): DoiCheckResult => ({ checked: 12, not_checked: 0, findings: [], counts: { error: 0, warning: 0, info: 0 }, ...over })
const bad: CheckFinding = { check: 'references.doi_resolves', severity: 'error', file: 'refs.bib', line: 9,
  message: 'DOI 10.1/gone (entry c) was not found at Crossref.', fix_hint: 'Check the DOI for typos, or replace the entry with one from your library. A made-up reference often shows up this way.' }
function show(tick = 0, onJump = vi.fn()) {
  const ui = (t: number) => <QueryClientProvider client={client}><DoiCheck manuscriptId="m" savedTick={t} onJump={onJump} /></QueryClientProvider>
  const r = render(ui(tick))
  return { ...r, again: (t: number) => r.rerender(ui(t)), onJump }
}
const press = () => fireEvent.click(screen.getByRole('button', { name: 'Check DOIs online' }))
afterEach(() => { vi.restoreAllMocks(); client.clear() })

test('idle: the button and the always-visible privacy line, nothing sent', () => {
  const spy = vi.spyOn(api, 'runDoiCheck')
  show()
  expect(screen.getByRole('button', { name: 'Check DOIs online' }).hasAttribute('disabled')).toBe(false)
  expect(screen.getByText('Sends only the DOI of each reference in your .bib files to Crossref, which paces anonymous requests, so a long list takes a while. Nothing else leaves your computer.')).toBeTruthy()
  expect(spy).not.toHaveBeenCalled()
})

test('running: the button is disabled and busy', async () => {
  let release!: (v: DoiCheckResult) => void
  vi.spyOn(api, 'runDoiCheck').mockReturnValue(new Promise((r) => { release = r }))
  show()
  press()
  const busy = await screen.findByRole('button', { name: 'Checking DOIs…' })
  expect(busy.hasAttribute('disabled')).toBe(true)
  expect(busy.getAttribute('aria-busy')).toBe('true')
  release(done())
  await screen.findByText('All 12 DOIs resolve.')
})

test('all resolve: plural, singular, and the not-checked note', async () => {
  const spy = vi.spyOn(api, 'runDoiCheck').mockResolvedValue(done({ checked: 1 }))
  show()
  press()
  expect(await screen.findByText('All 1 DOI resolves.')).toBeTruthy()
  spy.mockResolvedValue(done({ checked: 12, not_checked: 3 }))
  press()
  expect(await screen.findByText('All 12 DOIs resolve. 3 not checked (limit reached).')).toBeTruthy()
})

test('no DOIs in the bib files', async () => {
  vi.spyOn(api, 'runDoiCheck').mockResolvedValue(done({ checked: 0 }))
  show()
  press()
  expect(await screen.findByText('No DOIs found in your .bib files.')).toBeTruthy()
})

test('findings show severity text, file:line and the hint, and a click jumps', async () => {
  vi.spyOn(api, 'runDoiCheck').mockResolvedValue(done({ checked: 2, findings: [bad], counts: { error: 1, warning: 0, info: 0 } }))
  const { onJump } = show()
  press()
  fireEvent.click(await screen.findByRole('button', { name: /was not found at Crossref.*refs\.bib:9/ }))
  expect(onJump).toHaveBeenCalledWith('refs.bib', 9)
  expect(screen.getByText('error')).toBeTruthy()
  expect(screen.getByText(/A made-up reference often shows up/)).toBeTruthy()
})

test('stale after a save', async () => {
  vi.spyOn(api, 'runDoiCheck').mockResolvedValue(done())
  const { again } = show(0)
  press()
  await screen.findByText('All 12 DOIs resolve.')
  again(1)
  expect(await screen.findByText("You've edited since this check. Press again.")).toBeTruthy()
})

test('a network error shows the alert and a Sileo toast, and the button retries', async () => {
  const toast = vi.spyOn(sileo, 'error').mockReturnValue('' as never)
  vi.spyOn(api, 'runDoiCheck').mockRejectedValue(new ApiError('boom', 502, {}))
  show()
  press()
  expect((await screen.findByRole('alert')).textContent).toBe("Couldn't reach Crossref. Try again.")
  expect(toast).toHaveBeenCalledWith({ title: "Couldn't check the DOIs" })
  expect(screen.getByRole('button', { name: 'Check DOIs online' }).hasAttribute('disabled')).toBe(false)
})

test('Crossref switched off in Settings: its own text, no toast', async () => {
  const toast = vi.spyOn(sileo, 'error').mockReturnValue('' as never)
  vi.spyOn(api, 'runDoiCheck').mockRejectedValue(new ApiError('crossref_disabled', 422, { detail: 'crossref_disabled' }))
  show()
  press()
  expect((await screen.findByRole('alert')).textContent).toBe('Crossref is turned off in Settings → Paper sources.')
  await waitFor(() => expect(toast).not.toHaveBeenCalled())
})
