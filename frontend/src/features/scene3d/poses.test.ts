import { describe, expect, it } from 'vitest'
import { downloadPose } from './poses'

describe('downloadPose', () => {
  it('gathers the dust with the percent, short of the full mark until the download is done', () => {
    expect(downloadPose({ status: 'idle', percent: 0 }, 0).gather).toBe(0)
    expect(downloadPose({ status: 'downloading', percent: 0 }, 0).gather).toBe(0) // total 0 at the start
    expect(downloadPose({ status: 'downloading', percent: 50 }, 0).gather).toBeCloseTo(0.45, 9)
    expect(downloadPose({ status: 'downloading', percent: 100 }, 0)).toMatchObject({ gather: 0.9, card: 0 })
  })

  it('clamps a percent out of range or missing', () => {
    expect(downloadPose({ status: 'downloading', percent: 140 }, 0).gather).toBe(0.9)
    expect(downloadPose({ status: 'downloading', percent: Number.NaN }, 0).gather).toBe(0)
  })

  it('once done, forms the card, sweeps the highlighter and then holds', () => {
    expect(downloadPose({ status: 'done', percent: 100 }, 0)).toMatchObject({ gather: 1, card: 0 })
    expect(downloadPose({ status: 'done', percent: 100 }, 5)).toMatchObject({ gather: 1, card: 1, sweep: 1 })
  })

  it('scatters the dust again on an error', () => {
    expect(downloadPose({ status: 'error', percent: 60 }, 0)).toMatchObject({ gather: 0, card: 0, sweep: 0 })
  })
})
