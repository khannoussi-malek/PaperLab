// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { loadPagesWith, useRoute } from './route'

const faded = vi.hoisted(() => [] as string[])
vi.mock('@/components/motion', () => ({
  withViewTransition: (update: () => void) => {
    faded.push(window.location.hash)
    update()
  },
}))

function Where() {
  return <p>{useRoute().name}</p>
}

// jsdom fires hashchange itself, after the current task.
const go = (hash: string) =>
  act(async () => {
    window.location.hash = hash
    await new Promise((resolve) => setTimeout(resolve, 0))
  })

afterEach(async () => {
  loadPagesWith(() => undefined)
  window.location.hash = ''
  await new Promise((resolve) => setTimeout(resolve, 0)) // its hashchange lands here, not in the next test
  faded.length = 0
})

test("a new page fades in only once its code has loaded, so the fade shows the page and not its Loading…", async () => {
  let arrive = () => {}
  const loading = new Promise<void>((resolve) => (arrive = resolve))
  const asked: string[] = []
  loadPagesWith((route) => {
    asked.push(route.name)
    return loading
  })
  render(<Where />)
  await go('#/settings')
  expect(asked).toEqual(['settings'])
  expect(faded).toEqual([]) // still waiting for the page's code
  await act(async () => arrive())
  expect(faded).toEqual(['#/settings'])
  expect(screen.getByText('settings')).toBeInTheDocument()
})

test("a page whose code can't load still opens, so its own Try again shows", async () => {
  loadPagesWith(() => Promise.reject(new Error('chunk failed')))
  render(<Where />)
  await go('#/graph')
  await act(async () => {})
  expect(screen.getByText('graph')).toBeInTheDocument()
})

test('a slow page overtaken by a faster navigation never fades in late', async () => {
  let arriveSettings = () => {}
  const settings = new Promise<void>((resolve) => (arriveSettings = resolve))
  loadPagesWith((route) => (route.name === 'settings' ? settings : Promise.resolve()))
  render(<Where />)
  await go('#/settings')
  await go('#/graph')
  expect(faded).toEqual(['#/graph'])
  await act(async () => arriveSettings())
  expect(faded).toEqual(['#/graph']) // no second fade of graph onto graph
  expect(screen.getByText('graph')).toBeInTheDocument()
})

test("a page whose code hangs opens after a short wait anyway, to show its own Loading…", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  try {
    loadPagesWith(() => new Promise(() => {}))
    render(<Where />)
    await go('#/notes')
    expect(faded).toEqual([])
    await act(async () => vi.advanceTimersByTime(2100))
    expect(faded).toEqual(['#/notes'])
  } finally {
    vi.useRealTimers()
  }
})
