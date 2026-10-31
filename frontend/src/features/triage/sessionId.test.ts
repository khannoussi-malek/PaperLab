import { afterEach, describe, expect, it, vi } from 'vitest'
import { closeSession, openSession } from './sessionId'

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

describe('session id', () => {
  it('is the same on a second open (a reload), per scope', () => {
    const a = openSession('all')
    expect(openSession('all')).toBe(a)
    expect(openSession('ws1')).not.toBe(a)
    expect(sessionStorage.getItem('paperlab-triage-session:all')).toBe(a)
  })
  it('is new after closeSession', () => {
    const a = openSession('all')
    closeSession('all')
    expect(openSession('all')).not.toBe(a)
  })
  it('works with sessionStorage throwing, and stays stable in memory', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked') })
    const a = openSession('mem')
    expect(a).toBeTruthy()
    expect(openSession('mem')).toBe(a)
    closeSession('mem')
    expect(openSession('mem')).not.toBe(a)
  })
})
