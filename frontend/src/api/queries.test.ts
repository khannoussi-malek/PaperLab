import { describe, expect, it } from 'vitest'
import type { Paper, SearchRun } from './client'
import { PAPERS_POLL_MS, papersPollInterval, searchRunPollInterval } from './queries'

const paper = (status: string) => ({ status }) as Paper
const run = (status: string) => ({ status }) as SearchRun

describe('papersPollInterval', () => {
  it('polls while any paper is still ingesting', () => {
    expect(papersPollInterval([paper('ready'), paper('extracting')])).toBe(PAPERS_POLL_MS)
  })

  it('stops once every paper is ready or failed, or before the first load', () => {
    expect(papersPollInterval([paper('ready'), paper('failed')])).toBe(false)
    expect(papersPollInterval(undefined)).toBe(false)
  })
})

describe('searchRunPollInterval', () => {
  it('polls while the run is still running', () => {
    expect(searchRunPollInterval(run('running'))).toBe(PAPERS_POLL_MS)
  })

  it('stops once the run is no longer running, or before the first load', () => {
    expect(searchRunPollInterval(run('exhausted'))).toBe(false)
    expect(searchRunPollInterval(undefined)).toBe(false)
  })
})
