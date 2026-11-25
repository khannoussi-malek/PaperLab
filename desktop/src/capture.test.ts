import { describe, expect, it } from 'vitest'
import { captureArgs, captureBinary, createCapture, MAX_RESTARTS, shortcutLabel, type Child } from './capture'

type FakeChild = Child & { sent: string[]; killed: boolean; exit(code: number | null): void }

function fakeSpawn() {
  const children: FakeChild[] = []
  const calls: { bin: string; args: string[] }[] = []
  const spawn = (bin: string, args: string[]): Child => {
    let listener: (code: number | null) => void = () => {}
    const child: FakeChild = {
      sent: [],
      killed: false,
      send(line) {
        child.sent.push(line)
      },
      kill() {
        child.killed = true
      },
      onExit(callback) {
        listener = callback
      },
      exit(code) {
        listener(code)
      },
    }
    calls.push({ bin, args })
    children.push(child)
    return child
  }
  return { spawn, children, calls }
}

const quiet = () => {}

describe('Quick Capture helper', () => {
  it('is started with the API port, its shortcut and commands on stdin', () => {
    const base = ['--port', '5190', '--shortcut', 'ctrl+alt+p', '--stdin']
    expect(captureArgs(5190, 'ctrl+alt+p')).toEqual(base)
    expect(captureArgs(5190, 'ctrl+alt+p', { animation: false })).toEqual([...base, '--no-galaxy'])
    expect(captureArgs(5190, 'ctrl+alt+p', { float: true })).toEqual([...base, '--float'])
    expect(captureBinary('/Res')).toBe('/Res/capture/paperlab-capture')
    expect(shortcutLabel('ctrl+alt+p')).toBe('⌃⌥P')
    expect(shortcutLabel('cmd+shift+k')).toBe('⌘⇧K')
  })

  it('starts once, shows on demand and stops for good on quit', () => {
    const fake = fakeSpawn()
    const capture = createCapture({ spawn: fake.spawn, bin: '/b', port: 5190, shortcut: 'ctrl+alt+p', log: quiet })
    capture.start()
    capture.start() // already running: no second helper
    expect(fake.calls).toHaveLength(1)
    capture.show()
    expect(fake.children[0].sent).toEqual(['show\n'])
    capture.stop()
    expect(fake.children[0].killed).toBe(true)
    fake.children[0].exit(0) // its exit after a stop starts nothing
    expect(fake.calls).toHaveLength(1)
    expect(capture.running()).toBe(false)
  })

  it(`restarts a helper that dies, at most ${MAX_RESTARTS} times`, () => {
    const fake = fakeSpawn()
    const logged: string[] = []
    const capture = createCapture({ spawn: fake.spawn, bin: '/b', port: 5190, shortcut: 's', log: (line) => logged.push(line) })
    capture.start()
    for (let n = 0; n < MAX_RESTARTS + 2; n++) fake.children.at(-1)!.exit(1)
    expect(fake.calls).toHaveLength(1 + MAX_RESTARTS)
    expect(capture.running()).toBe(false)
    expect(logged.at(-1)).toMatch(/not restarted/)
  })

  it('waits for the stopped helper to exit before going on, so two never hold the shortcut', () => {
    const fake = fakeSpawn()
    const capture = createCapture({ spawn: fake.spawn, bin: '/b', port: 5190, shortcut: 's', log: quiet })
    capture.start()
    let next = 0
    capture.stop(() => (next += 1))
    expect(next).toBe(0)
    fake.children[0].exit(null)
    expect(next).toBe(1)
    capture.stop(() => (next += 1)) // none running: at once
    expect(next).toBe(2)
  })

  it('a second stop while the first still waits goes on once, after the exit (two quick switch flips)', () => {
    const fake = fakeSpawn()
    const capture = createCapture({ spawn: fake.spawn, bin: '/b', port: 5190, shortcut: 's', log: quiet })
    capture.start()
    const went: string[] = []
    capture.stop(() => went.push('first'))
    capture.stop(() => went.push('second'))
    expect(went).toEqual([])
    fake.children[0].exit(null)
    expect(went).toEqual(['second'])
  })

  it('can be started again after a stop (the switch turned back on)', () => {
    const fake = fakeSpawn()
    const capture = createCapture({ spawn: fake.spawn, bin: '/b', port: 5190, shortcut: 's', log: quiet })
    capture.start()
    capture.stop()
    capture.start()
    expect(fake.calls).toHaveLength(2)
    expect(capture.running()).toBe(true)
  })
})
