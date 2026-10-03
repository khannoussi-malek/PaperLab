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

test('refogs a running scene when the app theme (the dark class on html) changes', async () => {
  const { running, load } = fakeDirector()
  render(<Scene3D load={load} input={{ n: 1 }} canDraw={() => true} />)
  await act(() => Promise.resolve())
  running.refog.mockClear()
  try {
    await act(async () => {
      document.documentElement.classList.add('dark')
      await Promise.resolve()
    })
    expect(running.refog).toHaveBeenCalled()
  } finally {
    document.documentElement.classList.remove('dark')
  }
})

test('a rejected load shows the fallback and leaves no canvas behind', async () => {
  render(<Scene3D load={() => Promise.reject(new Error('chunk'))} input={{}} fallback={<p>plain</p>} canDraw={() => true} />)
  await act(() => Promise.resolve())
  expect(screen.getByText('plain')).toBeInTheDocument()
  expect(document.querySelector('canvas')).toBeNull()
})

test('a lost WebGL context disposes the scene once and falls back to the plain UI', async () => {
  const { running, load } = fakeDirector()
  render(<Scene3D load={load} input={{ n: 1 }} fallback={<p>plain</p>} canDraw={() => true} />)
  await act(() => Promise.resolve())
  act(() => void document.querySelector('canvas')!.dispatchEvent(new Event('webglcontextlost')))
  expect(running.dispose).toHaveBeenCalledOnce()
  expect(screen.getByText('plain')).toBeInTheDocument()
  expect(document.querySelector('canvas')).toBeNull()
})

test('a director whose frame throws is disposed and replaced by the fallback', async () => {
  const { running, load } = fakeDirector()
  running.frame.mockImplementation(() => {
    throw new Error('boom')
  })
  const cancel = vi.fn()
  vi.stubGlobal('cancelAnimationFrame', cancel)
  render(<Scene3D load={load} input={{ n: 1 }} fallback={<p>plain</p>} canDraw={() => true} />)
  await act(() => Promise.resolve())
  tick(1000)
  expect(running.dispose).toHaveBeenCalledOnce()
  expect(screen.getByText('plain')).toBeInTheDocument()
  expect(cancel).toHaveBeenCalled() // the loop stopped
})

test('unmounting a live scene disposes it once and never takes the lost-context path', async () => {
  const { running, load } = fakeDirector()
  const { unmount } = render(<Scene3D load={load} input={{ n: 1 }} canDraw={() => true} />)
  await act(() => Promise.resolve())
  const canvas = document.querySelector('canvas')!
  running.dispose.mockImplementation(() => void canvas.dispatchEvent(new Event('webglcontextlost')))
  unmount()
  expect(running.dispose).toHaveBeenCalledOnce()
})

test('the wrapper centres the fallback while the scene loads', () => {
  const { load } = fakeDirector()
  const { container } = render(<Scene3D load={load} input={{ n: 1 }} className="x" canDraw={() => true} />)
  expect(container.firstElementChild).toHaveClass('grid', 'place-items-center', 'x')
})
