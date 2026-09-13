import { describe, expect, it } from 'vitest'
import type { Paper } from './client'
import { PAPERS_POLL_MS, papersPollInterval } from './queries'

const paper = (status: string) => ({ status }) as Paper

describe('papersPollInterval', () => {
  it('polls while any paper is still ingesting', () => {
    expect(papersPollInterval([paper('ready'), paper('extracting')])).toBe(PAPERS_POLL_MS)
  })

  it('stops once every paper is ready or failed, or before the first load', () => {
    expect(papersPollInterval([paper('ready'), paper('failed')])).toBe(false)
    expect(papersPollInterval(undefined)).toBe(false)
  })
})
