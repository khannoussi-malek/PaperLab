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

afterEach(() => {
  loadPagesWith(() => undefined)
  faded.length = 0
  window.location.hash = ''
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
