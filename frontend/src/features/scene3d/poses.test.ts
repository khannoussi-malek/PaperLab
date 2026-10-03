import { describe, expect, it } from 'vitest'
import { CHAT_LOOP, chatPose, downloadPose, libraryPose } from './poses'

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

  it('shows the formed mark at once when the model was already there', () => {
    const pose = downloadPose({ status: 'ready', percent: 100 }, 0)
    expect(pose).toMatchObject({ gather: 1, card: 1, sweep: 1 })
    expect(pose.flash).toBeCloseTo(0, 1)
  })
})

describe('libraryPose', () => {
  it('crosses the sheen every 6 s and stacks nothing while idle', () => {
    expect(libraryPose(0.5, null)).toEqual({ sheen: 0, landed: [0, 0, 0] })
    expect(libraryPose(5.3, null).sheen).toBeCloseTo(0.5, 9)
  })

  it('lands three cards one after another while uploading, and starts again for a long upload', () => {
    expect(libraryPose(0, 0).landed).toEqual([0, 0, 0])
    const mid = libraryPose(0, 0.7).landed
    expect(mid[0]).toBeGreaterThan(mid[1])
    expect(mid[1]).toBeGreaterThanOrEqual(mid[2])
    expect(libraryPose(0, 2.0).landed).toEqual([1, 1, 1])
    // 3.1 % 2.4 is 0.7000000000000002: compare closely, not exactly.
    const again = libraryPose(0, 2.4 + 0.7).landed
    libraryPose(0, 0.7).landed.forEach((k, i) => expect(again[i]).toBeCloseTo(k, 9))
  })
})

describe('chatPose', () => {
  it('lifts the wire, then the note, then lands the light, on a loop', () => {
    const at = (u: number) => chatPose('thinking', u * CHAT_LOOP.thinking)
    expect(at(0)).toMatchObject({ wire: 0, note: 0, light: 0 })
    expect(at(0.33).wire).toBeGreaterThan(at(0.33).note)
    expect(at(0.75).light).toBeGreaterThan(0)
    expect(chatPose('thinking', 0.4 + CHAT_LOOP.thinking).wire).toBeCloseTo(chatPose('thinking', 0.4).wire, 9)
  })

  it('runs faster while finding sources than while writing', () => {
    expect(CHAT_LOOP.sources).toBeLessThan(CHAT_LOOP.thinking)
    expect(chatPose('sources', 0.5).wire).toBeGreaterThan(chatPose('thinking', 0.5).wire)
  })
})
