// @vitest-environment jsdom
import { act, renderHook } from '@testing-library/react'
import type { MouseEvent } from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { useCaptureDrag } from './useCaptureDrag'

let page: HTMLElement
beforeEach(() => {
  page = document.createElement('div')
  page.className = 'pdf-page'
  page.dataset.page = '3'
  page.getBoundingClientRect = () => ({ left: 0, top: 0, width: 600, height: 800, right: 600, bottom: 800, x: 0, y: 0, toJSON() {} })
  document.body.append(page)
})
afterEach(() => page.remove())

const at = (x: number, y: number, buttons = 1) =>
  ({ button: 0, buttons, clientX: x, clientY: y, target: page, preventDefault() {} }) as unknown as MouseEvent

function drag(result: { current: ReturnType<typeof useCaptureDrag> }) {
  act(() => result.current.startDrag(at(10, 10)))
  act(() => result.current.moveDrag(at(200, 150)))
  act(() => result.current.endDrag(at(200, 150, 0)))
}

test('figure and table modes exclude each other', () => {
  const { result } = renderHook(() => useCaptureDrag(1, vi.fn()))
  act(() => result.current.setDrawingFigure(true))
  expect(result.current.drawingFigure).toBe(true)
  act(() => result.current.setCapturing(true))
  expect(result.current.capturing).toBe(true)
  expect(result.current.drawingFigure).toBe(false)
  act(() => result.current.setDrawingFigure(true))
  expect(result.current.capturing).toBe(true) // any mode counts as capturing
  expect(result.current.drawingFigure).toBe(true)
})

test('Escape leaves either mode', () => {
  const { result } = renderHook(() => useCaptureDrag(1, vi.fn()))
  act(() => result.current.setDrawingFigure(true))
  act(() => void window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })))
  expect(result.current.drawingFigure).toBe(false)
  act(() => result.current.setCapturing(true))
  act(() => void window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })))
  expect(result.current.capturing).toBe(false)
})

test('a finished figure drag calls onFigure, opens no capture and leaves the mode', () => {
  const onFigure = vi.fn()
  const { result } = renderHook(() => useCaptureDrag(1, onFigure))
  act(() => result.current.setDrawingFigure(true))
  drag(result)
  expect(onFigure).toHaveBeenCalledWith(3, [10, 10, 200, 150])
  expect(result.current.capture).toBeNull()
  expect(result.current.drawingFigure).toBe(false)
  expect(result.current.capturing).toBe(false)
})

test('a table drag still sets capture', () => {
  const onFigure = vi.fn()
  const { result } = renderHook(() => useCaptureDrag(1, onFigure))
  act(() => result.current.setCapturing(true))
  drag(result)
  expect(result.current.capture).toEqual({ page: 3, region: [10, 10, 200, 150] })
  expect(onFigure).not.toHaveBeenCalled()
  expect(result.current.capturing).toBe(false)
})

test('tableMode is only the table mode, and each toggle switches to the other mode', () => {
  const { result } = renderHook(() => useCaptureDrag(1, vi.fn()))
  act(() => result.current.setDrawingFigure(true))
  expect(result.current.tableMode).toBe(false)
  act(() => result.current.setCapturing(true))
  expect(result.current.tableMode).toBe(true)
  expect(result.current.drawingFigure).toBe(false)
  act(() => result.current.setDrawingFigure(true))
  expect(result.current.tableMode).toBe(false)
  expect(result.current.drawingFigure).toBe(true)
})
