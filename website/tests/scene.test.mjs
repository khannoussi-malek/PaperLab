// The scroll scene's maths: where the reader is between the home page's sections.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { blendAt, sceneIndex } from '../src/lib/scene/scroll.ts'

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
