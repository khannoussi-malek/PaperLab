// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { MAX_DT, Scene3D, type Director } from './Scene3D'

let frames: FrameRequestCallback[] = []
beforeEach(() => {
  frames = []
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => frames.push(cb))
  vi.stubGlobal('cancelAnimationFrame', () => undefined)
  // jsdom has no matchMedia; the wrapper listens for theme changes through it.
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
})
const tick = (ms: number) => act(() => frames.splice(0).forEach((cb) => cb(ms)))

function fakeDirector() {
  const running = { resize: vi.fn(), frame: vi.fn(), refog: vi.fn(), dispose: vi.fn() }
  const director: Director<{ n: number }> = () => running
  return { running, load: vi.fn(() => Promise.resolve({ default: director })) }
}

test('without WebGL or with reduced motion it shows only the fallback and never loads three.js', () => {
  const { load } = fakeDirector()
  render(<Scene3D load={load} input={{ n: 1 }} fallback={<p>plain</p>} canDraw={() => false} />)
  expect(screen.getByText('plain')).toBeInTheDocument()
  expect(document.querySelector('canvas')).toBeNull()
  expect(load).not.toHaveBeenCalled()
})

test('runs the director on an aria-hidden canvas, feeding it the latest input, and disposes it on unmount', async () => {
  const { running, load } = fakeDirector()
  const { rerender, unmount } = render(<Scene3D load={load} input={{ n: 1 }} canDraw={() => true} />)
  await act(() => Promise.resolve())
  expect(document.querySelector('canvas')).toHaveAttribute('aria-hidden', 'true')
  tick(1000)
  tick(1016)
  rerender(<Scene3D load={load} input={{ n: 2 }} canDraw={() => true} />)
  tick(1032)
  expect(running.frame).toHaveBeenLastCalledWith(expect.any(Number), expect.any(Number), { n: 2 })
  unmount()
  expect(running.dispose).toHaveBeenCalledOnce()
})

test('caps a frame step, so coming back from a hidden tab never jumps the scene ahead', async () => {
  const { running, load } = fakeDirector()
  render(<Scene3D load={load} input={{ n: 1 }} canDraw={() => true} />)
  await act(() => Promise.resolve())
  tick(1000)
  tick(61_000) // a minute away
  const [, dt] = running.frame.mock.calls.at(-1)!
  expect(dt).toBeLessThanOrEqual(MAX_DT)
})

test('a director that fails to load or start leaves the fallback, and throws nothing', async () => {
  const failing = vi.fn(() => Promise.reject(new Error('chunk')))
  render(<Scene3D load={failing} input={{}} fallback={<p>plain</p>} canDraw={() => true} />)
  await act(() => Promise.resolve())
  expect(screen.getByText('plain')).toBeInTheDocument()

  const throwing: Director<object> = () => {
    throw new Error('no context')
  }
  render(<Scene3D load={() => Promise.resolve({ default: throwing })} input={{}} fallback={<p>still plain</p>} canDraw={() => true} />)
  await act(() => Promise.resolve())
  expect(screen.getByText('still plain')).toBeInTheDocument()
})
