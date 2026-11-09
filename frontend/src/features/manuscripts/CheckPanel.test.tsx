// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type CheckFinding, type CheckRunResult } from '@/api/client'
import { CheckPanel } from './CheckPanel'

const f = (i: number, over: Partial<CheckFinding> = {}): CheckFinding => ({
  check: 'citations.missing_keys', severity: 'error', file: i === 0 ? 'refs/a.tex' : 'main.tex', line: i + 3,
  message: `Cited key k${i} matches no paper in your library or your .bib files, so LaTeX prints [?].`, fix_hint: 'Add it.', ...over })
const result = (findings: CheckFinding[], ran = ['citations.missing_keys']): CheckRunResult => ({
  ran, findings,
  counts: { error: findings.filter((x) => x.severity === 'error').length, warning: findings.filter((x) => x.severity === 'warning').length, info: 0 } })
const none = result([])
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function show(tick = 0, at = 't1', onJump = vi.fn()) {
  const ui = (t: number, a: string) => (
    <QueryClientProvider client={client}><CheckPanel manuscriptId="m" savedTick={t} compiledAt={a} onJump={onJump} /></QueryClientProvider>)
  const r = render(ui(tick, at))
  return { ...r, again: (t: number, a = at) => r.rerender(ui(t, a)), onJump }
}
function mockApi(badge: CheckRunResult | Error, full: CheckRunResult | Error | Promise<CheckRunResult> = none) {
  vi.spyOn(api, 'listManuscriptChecks').mockResolvedValue([{ name: 'citations.missing_keys', cost: 'cheap', description: 'Cited keys that match no paper or .bib entry' }])
  return vi.spyOn(api, 'runChecks').mockImplementation(async (_id, body) => {
    const v = body.cost === 'cheap' ? badge : await full
    if (v instanceof Error) throw v
    return v
  })
}
afterEach(() => { vi.restoreAllMocks(); client.clear() })

test('idle: a one-line strip with the title and the Check button, no body', async () => {
  mockApi(none)
  show()
  expect(await screen.findByText('No quick problems')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Check' })).toBeTruthy()
  expect(screen.queryByText(/Nothing found/)).toBeNull()
})

test('missing keys show in the body before any press, with a jump (what MissingCites did)', async () => {
  mockApi(result([f(0), f(1)]))
  const { onJump } = show()
  expect(await screen.findByText('Cited keys that match no paper or .bib entry')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /k0.*refs\/a\.tex:3/ }))
  expect(onJump).toHaveBeenCalledWith('refs/a.tex', 3)
  expect(screen.queryByText(/You've edited since/)).toBeNull() // quick findings are never "stale"
})

test('quick findings follow the badge: a new compile refetches them, a save invalidation too', async () => {
  const spy = mockApi(result([f(0)]))
  const { again } = show(0, 't1')
  await screen.findByText(/k0/)
  again(0, 't2')
  await waitFor(() => expect(spy.mock.calls.filter(([, b]) => b.cost === 'cheap')).toHaveLength(2))
  await client.invalidateQueries({ queryKey: ['manuscripts', 'm'] })
  await waitFor(() => expect(spy.mock.calls.filter(([, b]) => b.cost === 'cheap')).toHaveLength(3))
})

test('badge: absent while pending, then the error+warning count', async () => {
  mockApi(result([f(0), f(1, { severity: 'warning' })]))
  show()
  expect(screen.queryByLabelText('Quick problems')).toBeNull()
  expect((await screen.findByLabelText('Quick problems')).textContent).toBe('2')
})

test('badge fetch failure shows ? with an explanation and no toast', async () => {
  const toast = vi.spyOn(sileo, 'error')
  mockApi(new ApiError('boom', 500, {}))
  show()
  const badge = await screen.findByLabelText('Quick problems')
  expect(badge.textContent).toBe('?')
  expect(badge.getAttribute('title')).toBe("Couldn't refresh the quick checks")
  expect(toast).not.toHaveBeenCalled()
})

test('Check runs everything; while it runs the button says Checking… and is disabled', async () => {
  let release!: (r: CheckRunResult) => void
  const spy = mockApi(none, new Promise<CheckRunResult>((r) => { release = r }))
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  const busy = await screen.findByRole('button', { name: 'Checking…' })
  expect((busy as HTMLButtonElement).disabled).toBe(true)
  expect(spy).toHaveBeenCalledWith('m', {})
  release(none)
  expect(await screen.findByText('Nothing found. 1 check ran.')).toBeTruthy()
})

test('findings are grouped under the check description with severity text, hint, and a jump on click', async () => {
  mockApi(none, result([f(0), f(1)]))
  const { onJump } = show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  expect(await screen.findByText('Cited keys that match no paper or .bib entry')).toBeTruthy()
  expect(screen.getByText('2 errors')).toBeTruthy()
  expect(screen.getAllByText('Add it.')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: /k0.*refs\/a\.tex:3/ }))
  expect(onJump).toHaveBeenCalledWith('refs/a.tex', 3)
  expect(screen.getByRole('button', { name: /k1.*main\.tex:4/ })).toBeTruthy()
})

test('a finding with no file is shown but is not a button', async () => {
  mockApi(none, result([f(0, { file: null, line: null, message: 'General note' })]))
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  expect(await screen.findByText('General note')).toBeTruthy()
  expect(screen.queryByRole('button', { name: /General note/ })).toBeNull()
})

test('caps a group at 20 rows with "and 3 more"', async () => {
  mockApi(none, result(Array.from({ length: 23 }, (_, i) => f(i))))
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  expect(await screen.findByText('and 3 more')).toBeTruthy()
  expect(screen.getAllByRole('button', { name: /k\d+/ })).toHaveLength(20)
})

test('after an edit the old result stays with a stale line', async () => {
  mockApi(none, result([f(0)]))
  const { again } = show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  await screen.findByText(/k0/)
  expect(screen.queryByText("You've edited since this check. Press Check again.")).toBeNull()
  again(1)
  expect(await screen.findByText("You've edited since this check. Press Check again.")).toBeTruthy()
  expect(screen.getByText(/k0/)).toBeTruthy()
})

test('a failed run shows an alert and a Sileo toast, keeps the button as the retry, keeps the old result', async () => {
  const toast = vi.spyOn(sileo, 'error').mockReturnValue('' as never)
  const spy = mockApi(none, result([f(0)]))
  show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  await screen.findByText(/k0/)
  spy.mockImplementation(async (_id, body) => { if (body.cost === 'cheap') return none; throw new ApiError('boom', 500, {}) })
  fireEvent.click(screen.getByRole('button', { name: 'Check' }))
  expect((await screen.findByRole('alert')).textContent).toBe("Couldn't run the checks. Try again.")
  expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: "Couldn't run the checks" }))
  expect(screen.getByText(/k0/)).toBeTruthy()
  await waitFor(() => expect((screen.getByRole('button', { name: 'Check' }) as HTMLButtonElement).disabled).toBe(false))
})

test('a failed re-run after an edit keeps the stale line with the old result', async () => {
  const spy = mockApi(none, result([f(0)]))
  const { again } = show()
  fireEvent.click(await screen.findByRole('button', { name: 'Check' }))
  await screen.findByText(/k0/)
  again(1)
  expect(await screen.findByText("You've edited since this check. Press Check again.")).toBeTruthy()
  spy.mockImplementation(async (_id, body) => { if (body.cost === 'cheap') return none; throw new ApiError('boom', 500, {}) })
  fireEvent.click(screen.getByRole('button', { name: 'Check' }))
  await screen.findByRole('alert')
  expect(screen.getByText("You've edited since this check. Press Check again.")).toBeTruthy()
  expect(screen.getByText(/k0/)).toBeTruthy()
})

test('Nothing found only appears after a press, never from the quick run alone', async () => {
  mockApi(none)
  show()
  await screen.findByText('No quick problems')
  expect(screen.queryByText(/Nothing found/)).toBeNull()
})
