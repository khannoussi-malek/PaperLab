import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { createAutosave } from './autosave'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

test('saves 1 s after the last change', async () => {
  const save = vi.fn().mockResolvedValue({ conflict: false })
  const auto = createAutosave({ delayMs: 1000, save })
  auto.change('a')
  await vi.advanceTimersByTimeAsync(600)
  auto.change('ab')
  await vi.advanceTimersByTimeAsync(999)
  expect(save).not.toHaveBeenCalled()
  expect(auto.state).toBe('unsaved')
  await vi.advanceTimersByTimeAsync(1)
  expect(save).toHaveBeenCalledOnce()
  expect(save).toHaveBeenCalledWith('ab')
  expect(auto.state).toBe('saved')
})

test('flush saves now', async () => {
  const save = vi.fn().mockResolvedValue({ conflict: false })
  const auto = createAutosave({ delayMs: 1000, save })
  auto.change('x')
  await auto.flush()
  expect(save).toHaveBeenCalledWith('x')
  await vi.advanceTimersByTimeAsync(2000)
  expect(save).toHaveBeenCalledOnce()
})

test('conflict stops autosave', async () => {
  const save = vi.fn().mockResolvedValue({ conflict: true })
  const auto = createAutosave({ delayMs: 1000, save })
  auto.change('x')
  await vi.advanceTimersByTimeAsync(1000)
  expect(auto.state).toBe('conflict')
  auto.change('xy')
  await auto.flush()
  await vi.advanceTimersByTimeAsync(5000)
  expect(save).toHaveBeenCalledOnce()
  auto.reload()
  auto.change('z')
  await vi.advanceTimersByTimeAsync(1000)
  expect(save).toHaveBeenCalledTimes(2)
})
