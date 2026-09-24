import { describe, expect, it } from 'vitest'
import type { Hit, Paper, SearchRun } from './client'
import { PAPERS_POLL_MS, matchesEligibleHit, papersPollInterval, searchRunPollInterval } from './queries'

const paper = (status: string) => ({ status }) as Paper
const run = (status: string) => ({ status }) as SearchRun
const hit = (paperId: string | null, runId: string) => ({ paper_id: paperId, run_id: runId }) as Hit

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

describe('matchesEligibleHit', () => {
  it('matches a hit whose paper_id and run_id both match the eligibility response', () => {
    expect(matchesEligibleHit(hit('paper-1', 'run-1'), 'paper-1', 'run-1')).toBe(true)
  })

  it('does not match on run_id alone (same paper, different run)', () => {
    expect(matchesEligibleHit(hit('paper-1', 'run-1'), 'paper-1', 'run-2')).toBe(false)
  })

  it('does not match on paper_id alone (same run, different paper)', () => {
    expect(matchesEligibleHit(hit('paper-1', 'run-1'), 'paper-2', 'run-1')).toBe(false)
  })

  it('never matches a hit with no imported paper (paper_id null)', () => {
    expect(matchesEligibleHit(hit(null, 'run-1'), 'paper-1', 'run-1')).toBe(false)
  })
})
