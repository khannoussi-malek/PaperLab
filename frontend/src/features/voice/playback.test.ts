import { afterEach, expect, it, vi } from 'vitest'
import { createPlayback } from './playback'

class FakeSource {
  startedAt: number | null = null
  stopped = false
  onended: (() => void) | null = null
  connect = vi.fn()
  start(at: number) {
    this.startedAt = at
  }
  stop() {
    this.stopped = true
  }
}

function setup(onIdle?: () => void) {
  const sources: FakeSource[] = []
  const ctx = {
    currentTime: 0,
    createBuffer: (_channels: number, length: number, rate: number) => ({ duration: length / rate, copyToChannel: vi.fn() }),
    createBufferSource: () => {
      const source = new FakeSource()
      sources.push(source)
      return source
    },
  }
  const out = {} as AudioNode
  const playback = createPlayback(ctx as unknown as AudioContext, out, onIdle)
  const second = (seconds: number) => new Float32Array(seconds * 1000) // at 1000 Hz
  return { ctx, sources, playback, second, out }
}

afterEach(() => vi.restoreAllMocks())

it('schedules chunks back to back after a short lead', () => {
  const { playback, sources, second, out } = setup()
  playback.play(second(1), 1000)
  playback.play(second(2), 1000)
  expect(sources.map((s) => s.startedAt)).toEqual([0.05, 1.05])
  expect(sources[0].connect).toHaveBeenCalledWith(out)
  expect(playback.active()).toBe(true)
})

it('starts a late chunk at the current time plus the lead', () => {
  const { playback, sources, second, ctx } = setup()
  playback.play(second(1), 1000)
  ctx.currentTime = 5
  playback.play(second(1), 1000)
  expect(sources[1].startedAt).toBeCloseTo(5.05)
})

it('stop stops every live source and forgets what was scheduled', () => {
  const { playback, sources, second, ctx } = setup()
  playback.play(second(1), 1000)
  playback.play(second(1), 1000)
  ctx.currentTime = 0.5
  playback.stop()
  expect(sources.every((s) => s.stopped)).toBe(true)
  expect(playback.active()).toBe(false)
  expect(playback.playedSeconds()).toBe(0)
  playback.play(second(1), 1000) // the next turn starts from the clock again
  expect(sources[2].startedAt).toBeCloseTo(0.55)
})

it('counts only what has been heard, never the future or more than was scheduled', () => {
  const { playback, second, ctx } = setup()
  playback.play(second(2), 1000) // 0.05 to 2.05
  expect(playback.playedSeconds()).toBe(0)
  ctx.currentTime = 1.05
  expect(playback.playedSeconds()).toBeCloseTo(1)
  ctx.currentTime = 100
  expect(playback.playedSeconds()).toBeCloseTo(2)
})

it('tells the first chunk when it will be heard, once', () => {
  vi.spyOn(performance, 'now').mockReturnValue(1000)
  const onFirst = vi.fn()
  const { playback, second } = setup()
  playback.play(second(1), 1000, onFirst)
  playback.play(second(1), 1000)
  expect(onFirst).toHaveBeenCalledOnce()
  expect(onFirst).toHaveBeenCalledWith(1050)
})

it('reports idle when the last chunk ends by itself, not when stopped', () => {
  const onIdle = vi.fn()
  const { playback, sources, second } = setup(onIdle)
  playback.play(second(1), 1000)
  playback.play(second(1), 1000)
  sources[0].onended?.()
  expect(onIdle).not.toHaveBeenCalled()
  sources[1].onended?.()
  expect(onIdle).toHaveBeenCalledOnce()
  playback.play(second(1), 1000)
  playback.stop()
  expect(onIdle).toHaveBeenCalledOnce()
})
