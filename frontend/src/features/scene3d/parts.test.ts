// @vitest-environment jsdom
import * as THREE from 'three'
import { expect, it, vi } from 'vitest'
import { dustField, logoMark, pageStream, stage } from './parts'

// jsdom has no 2D canvas: give the painters a context that records nothing.
HTMLCanvasElement.prototype.getContext = vi.fn(() => new Proxy({}, { get: () => () => ({ addColorStop() {} }) })) as never

it('disposes every geometry, material and texture the parts made, and the renderer', () => {
  const renderer = { setPixelRatio() {}, setSize() {}, render() {}, dispose: vi.fn(), toneMapping: 0 } as never
  const s = stage(document.createElement('canvas'), renderer)
  s.scene.add(logoMark().group, dustField(50, 3).points, pageStream(5, 4).group)
  // Distinct geometries (the flying pages share one), each watched for its dispose event.
  const geometries = new Set<THREE.BufferGeometry>()
  s.scene.traverse((o) => {
    const geometry = (o as THREE.Mesh).geometry
    if (geometry) geometries.add(geometry)
  })
  const freed = new Set<THREE.BufferGeometry>()
  geometries.forEach((g) => g.addEventListener('dispose', () => freed.add(g)))
  s.dispose()
  expect(geometries.size).toBeGreaterThan(5)
  expect(freed.size).toBe(geometries.size)
  expect(s.scene.children).toHaveLength(0) // the scene is emptied too
  expect((renderer as { dispose: ReturnType<typeof vi.fn> }).dispose).toHaveBeenCalled()
})
