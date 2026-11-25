/**
 * Quick Capture (M65): the small native panel PaperLab starts beside itself. It finds a library paper or adds one from
 * any app on a global shortcut, through the stack's own API. This keeps it running: started once the stack answers,
 * restarted a few times if it dies, stopped when PaperLab quits or the switch goes off.
 */
import { spawn as spawnProcess } from 'node:child_process'
import { join } from 'node:path'

export const MAX_RESTARTS = 3
export const DEFAULT_SHORTCUT = 'ctrl+alt+p'

/** The running helper, as this module uses it. */
export type Child = {
  /** A line on its stdin: `show` opens the panel. */
  send(line: string): void
  kill(): void
  onExit(listener: (code: number | null) => void): void
}
export type Spawn = (bin: string, args: string[]) => Child

export type Capture = {
  start(): void
  show(): void
  /** Stops it for good; `then` runs once it has exited (at once when none is running). */
  stop(then?: () => void): void
  running(): boolean
}

type Options = {
  spawn: Spawn
  bin: string
  port: number
  shortcut: string
  look?: Look
  log: (line: string) => void
}

const SYMBOLS: Record<string, string> = { ctrl: '⌃', control: '⌃', alt: '⌥', option: '⌥', shift: '⇧', cmd: '⌘', command: '⌘', super: '⌘', meta: '⌘' }

/** "ctrl+alt+p" as macOS menus show it: ⌃⌥P. */
export const shortcutLabel = (shortcut: string) =>
  shortcut
    .split('+')
    .map((part) => SYMBOLS[part.trim().toLowerCase()] ?? part.trim().toUpperCase())
    .join('')

/** How the helper shows itself (Settings → Desktop app); each is read once, when it starts. */
export type Look = {
  /** The stars and papers behind the panel. On unless turned off. */
  animation?: boolean
  /** The floating paper over every app (M79). Off unless turned on. */
  float?: boolean
}

export const captureArgs = (port: number, shortcut: string, { animation = true, float = false }: Look = {}) => [
  '--port',
  String(port),
  '--shortcut',
  shortcut,
  '--stdin',
  ...(animation ? [] : ['--no-galaxy']),
  ...(float ? ['--float'] : []),
]

/** Packaged: electron-builder's extraResources put the binary for the app's arch here. */
export const captureBinary = (resourcesDir: string) => join(resourcesDir, 'capture', 'paperlab-capture')

export function createCapture({ spawn, bin, port, shortcut, look = {}, log }: Options): Capture {
  let child: Child | null = null
  let restarts = 0
  let stopped = false
  let afterExit: (() => void) | null = null

  function run() {
    const started = spawn(bin, captureArgs(port, shortcut, look))
    child = started
    started.onExit((code) => {
      if (child !== started) {
        // An older helper, already stopped: whoever waited for it to let go of the shortcut goes on now.
        const then = afterExit
        afterExit = null
        return then?.()
      }
      child = null
      if (stopped) return
      if (restarts >= MAX_RESTARTS) return log(`Quick Capture exited (${code}) ${restarts + 1} times; not restarted`)
      restarts += 1
      log(`Quick Capture exited (${code}); restarting (${restarts} of ${MAX_RESTARTS})`)
      run()
    })
  }

  return {
    start() {
      if (child !== null) return
      stopped = false
      run()
    },
    show() {
      child?.send('show\n')
    },
    stop(then) {
      stopped = true
      const running = child
      child = null
      if (running === null) return then?.()
      afterExit = then ?? null
      running.kill()
    },
    running: () => child !== null,
  }
}

/** The real helper: its stdin takes commands (closing it quits the helper too), its stderr goes to PaperLab's log. */
export function spawnChild(log: (line: string) => void): Spawn {
  return (bin, args) => {
    const proc = spawnProcess(bin, args, { stdio: ['pipe', 'ignore', 'pipe'] })
    proc.on('error', (error) => log(`Quick Capture could not start: ${String(error)}`))
    // A write to a helper that just died (EPIPE) must not become an uncaught exception in PaperLab's main process.
    proc.stdin?.on('error', (error) => log(`Quick Capture's input closed: ${String(error)}`))
    proc.stderr?.on('data', (data: Buffer) => log(`Quick Capture: ${data.toString().trimEnd()}`))
    return {
      send: (line) => void proc.stdin?.write(line),
      kill: () => void proc.kill(),
      onExit: (listener) => void proc.on('exit', listener),
    }
  }
}
