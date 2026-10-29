import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/api/client'
import { citeThis } from './citeThis'

afterEach(() => vi.restoreAllMocks())
const handle = (result: 'ok' | 'changed' = 'ok', can = true) => ({ canCite: vi.fn(async () => can), applyCite: vi.fn(async () => result) })

test('pins first, then inserts the key the pin answered with', async () => {
  const order: string[] = []
  vi.spyOn(api, 'pinPaper').mockImplementation(async () => { order.push('pin'); return { key: 'lewis2020' } })
  const h = { canCite: async () => true, applyCite: vi.fn(async () => { order.push('insert'); return 'ok' as const }) }
  expect(await citeThis({ manuscriptId: 'm', workspaceId: 'w', handle: h as never }, 'hash', 'p1')).toBeNull()
  expect(h.applyCite).toHaveBeenCalledWith('hash', 'lewis2020')
  expect(order).toEqual(['pin', 'insert'])
})

test('an unknown paper is added to the workspace, then pinned again', async () => {
  const pin = vi.spyOn(api, 'pinPaper').mockRejectedValueOnce(new ApiError('nope', 404, { detail: 'unknown_paper' })).mockResolvedValueOnce({ key: 'k2' })
  const add = vi.spyOn(api, 'addToWorkspace').mockResolvedValue(undefined)
  const h = handle()
  expect(await citeThis({ manuscriptId: 'm', workspaceId: 'w', handle: h as never }, 'hash', 'p1')).toBeNull()
  expect(add).toHaveBeenCalledWith('w', 'p1')
  expect(pin).toHaveBeenCalledTimes(2)
  expect(h.applyCite).toHaveBeenCalledWith('hash', 'k2')
})

test('a failed pin inserts nothing and says so', async () => {
  vi.spyOn(api, 'pinPaper').mockRejectedValue(new Error('boom'))
  const h = handle()
  expect(await citeThis({ manuscriptId: 'm', workspaceId: 'w', handle: h as never }, 'hash', 'p1')).toMatch(/boom/)
  expect(h.applyCite).not.toHaveBeenCalled()
})

test('a changed sentence is reported', async () => {
  vi.spyOn(api, 'pinPaper').mockResolvedValue({ key: 'k' })
  expect(await citeThis({ manuscriptId: 'm', workspaceId: 'w', handle: handle('changed') as never }, 'hash', 'p1')).toBe('That sentence changed. Check again.')
})

test('a sentence changed before the click: nothing is pinned or added and nothing is inserted', async () => {
  const pin = vi.spyOn(api, 'pinPaper')
  const add = vi.spyOn(api, 'addToWorkspace')
  const h = handle('ok', false)
  expect(await citeThis({ manuscriptId: 'm', workspaceId: 'w', handle: h as never }, 'hash', 'p1')).toBe('That sentence changed. Check again.')
  expect(pin).not.toHaveBeenCalled()
  expect(add).not.toHaveBeenCalled()
  expect(h.applyCite).not.toHaveBeenCalled()
})
