import { expect, it, vi } from 'vitest'
import { createInterruptDetector } from './interruptDetector'

const make = () => {
  const onTrigger = vi.fn()
  const detector = createInterruptDetector({ threshold: 0.7, sustainMs: 250, frameMs: 32, onTrigger })
  return { detector, onTrigger }
}
/** Feeds `count` frames of `p`, 32 ms apart from `from`; returns the time after the last one. */
const feed = (detector: ReturnType<typeof make>['detector'], count: number, p: number, playing: boolean, from = 0) => {
  for (let i = 0; i < count; i++) detector.frame(p, playing, from + i * 32)
  return from + count * 32
}

it('triggers once after 250 ms of voice at or above the threshold, with the first voiced frame time', () => {
  const { detector, onTrigger } = make()
  feed(detector, 7, 0.9, true) // 224 ms: not yet
  expect(onTrigger).not.toHaveBeenCalled()
  detector.frame(0.7, true, 224) // exactly at the threshold counts
  expect(onTrigger).toHaveBeenCalledOnce()
  expect(onTrigger).toHaveBeenCalledWith(0)
})

it('starts over after a dip', () => {
  const { detector, onTrigger } = make()
  const t = feed(detector, 7, 0.9, true)
  const dipped = feed(detector, 1, 0.3, true, t)
  feed(detector, 7, 0.9, true, dipped)
  expect(onTrigger).not.toHaveBeenCalled()
})

it('never triggers when nothing is playing', () => {
  const { detector, onTrigger } = make()
  feed(detector, 40, 0.99, false)
  expect(onTrigger).not.toHaveBeenCalled()
})

it('does not count voice from before playback began', () => {
  const { detector, onTrigger } = make()
  const t = feed(detector, 6, 0.9, false)
  feed(detector, 3, 0.9, true, t)
  expect(onTrigger).not.toHaveBeenCalled()
})
