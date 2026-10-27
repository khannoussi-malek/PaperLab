import { expect, it } from 'vitest'
import { hopAction, initialTotals, turnStep, zoomStep } from './deckGestures'

it('a flick is one step', () => expect(hopAction(-1)).toEqual({ type: 'step', by: -1 }))

it('a glide steps one card per 0.35 rad and keeps the remainder', () => {
  let [t, a] = turnStep(initialTotals, 0.2)
  expect(a).toBeNull()
  ;[t, a] = turnStep(t, 0.2)
  expect(a).toEqual({ type: 'step', by: 1 })
  expect(t.turn).toBeCloseTo(0.05)
  ;[, a] = turnStep(initialTotals, -0.4)
  expect(a).toEqual({ type: 'step', by: -1 })
})

it('spreading past 1.25 opens, closing past 0.8 shuts, and each resets', () => {
  let [t, a] = zoomStep(initialTotals, 1.15)
  expect(a).toBeNull()
  ;[t, a] = zoomStep(t, 1.1)
  expect(a).toEqual({ type: 'open' })
  expect(t.zoom).toBe(1)
  ;[t, a] = zoomStep(t, 0.85)
  ;[t, a] = zoomStep(t, 0.9)
  expect(a).toEqual({ type: 'close' })
})
