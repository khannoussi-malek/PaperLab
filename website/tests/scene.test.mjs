// The scroll scene's maths: where the reader is between the home page's sections.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { blendAt, sceneIndex, settleTarget } from '../src/lib/scene/scroll.ts'

test('sceneIndex is 0 before the first section, the last index past the end, and linear between', () => {
  const centers = [400, 1400, 2400]
  assert.equal(sceneIndex(centers, 100), 0)
  assert.equal(sceneIndex(centers, 400), 0)
  assert.equal(sceneIndex(centers, 900), 0.5)
  assert.equal(sceneIndex(centers, 1650), 1.25)
  assert.equal(sceneIndex(centers, 9000), 2)
  assert.equal(sceneIndex([], 500), 0)
})

test('blendAt interpolates per-section values by the float index', () => {
  assert.equal(blendAt([0, 10, 20], 1.5), 15)
  assert.equal(blendAt([0, 10], 7), 10)
  assert.equal(blendAt([4], 0.3), 4)
})

test('settleTarget moves on only after a third of the way to the next stop, else glides back', () => {
  const stops = [0, 900, 1800, 2700]
  assert.equal(settleTarget(stops, [], 120, 1), 0, 'a small nudge down: back to where it was')
  assert.equal(settleTarget(stops, [], 400, 1), 900, 'past a third: on to the next')
  assert.equal(settleTarget(stops, [], 1700, 1), 1800)
  assert.equal(settleTarget(stops, [], 1700, -1), 1800, 'a small nudge up: back down')
  assert.equal(settleTarget(stops, [], 1400, -1), 900, 'past a third up: on to the one above')
  assert.equal(settleTarget(stops, [], 3000, 1), 2700, 'past the last stop: back to it')
})

test('settleTarget leaves the page alone when it already rests on a stop', () => {
  assert.equal(settleTarget([0, 900], [], 901, 1), null)
  assert.equal(settleTarget([0, 900], [], 0, -1), null)
})

test('settleTarget lets a reader scroll freely inside a section taller than the screen', () => {
  const stops = [0, 900, 1500, 2600]
  const free = [[900, 1500]] // a tall section: its top stop, its bottom stop
  assert.equal(settleTarget(stops, free, 1200, 1), null)
  assert.equal(settleTarget(stops, free, 1550, 1), 1500, 'a nudge past its bottom: back to it')
  assert.equal(settleTarget(stops, free, 1950, 1), 2600, 'past a third beyond it: on to the next')
  assert.equal(settleTarget(stops, free, 850, -1), 900, 'a nudge up out of it: back to its top')
  assert.equal(settleTarget(stops, free, 500, -1), 0)
})
