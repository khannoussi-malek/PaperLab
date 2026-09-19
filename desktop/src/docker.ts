/**
 * Docker for the desktop app (spec §5): find the docker binary, run it without a shell and under a time limit, and the
 * commands the launch needs. Every command and its exit code goes to main.log.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { accessSync, constants, createWriteStream, statSync } from 'node:fs'
import { join, posix, win32 } from 'node:path'
import { pipeline } from 'node:stream/promises'
import { createGzip } from 'node:zlib'
import type { Log } from './log'
import { compareVersions } from './updates'

export const IMAGE = 'ghcr.io/khannoussi-malek/paperlab'
/** Time limits in ms. null: none, since a pull reports its progress instead. */
export const LIMITS = { info: 15_000, version: 15_000, up: 300_000, stop: 30_000, pull: null } as const

export type Result = { code: number; stdout: string; stderr: string; timedOut: boolean }
export type RunOptions = {
  env: NodeJS.ProcessEnv
  timeoutMs: number | null
  onLine?: (line: string) => void
  signal?: AbortSignal
}
export type Runner = (file: string, args: readonly string[], options: RunOptions) => Promise<Result>
export type StackInfo = { dataDir: string; version: string; port: number }

/** Where Docker installs its CLI on macOS, Linux and WSL, in scripts/paperlab-mcp's order (a test keeps them equal). */
function posixFallbacks(home: string): string[] {
  return [
    `${home}/.docker/bin/docker`,
    `${home}/.rd/bin/docker`,
    '/usr/local/bin/docker',
    '/opt/homebrew/bin/docker',
    '/usr/bin/docker',
    `${home}/.orbstack/bin/docker`,
    '/Applications/Docker.app/Contents/Resources/bin/docker',
    '/mnt/wsl/docker-desktop/cli-tools/usr/bin/docker',
  ]
}

/** The fixed places. PAPERLAB_DOCKER_PATHS (tests; space-separated, empty for none) replaces them, as in the script. */
export function fallbackPaths(platform: NodeJS.Platform, env: NodeJS.ProcessEnv, home: string): string[] {
  if (env.PAPERLAB_DOCKER_PATHS !== undefined) return env.PAPERLAB_DOCKER_PATHS.split(' ').filter(Boolean)
  if (platform === 'win32') {
    return [win32.join(env.ProgramFiles ?? 'C:\\Program Files', 'Docker', 'Docker', 'resources', 'bin', 'docker.exe')]
  }
  return posixFallbacks(home)
}

/** Windows spells it Path; a copied environment must keep one key, whatever its case. */
const pathKey = (env: NodeJS.ProcessEnv) => Object.keys(env).find((key) => key.toUpperCase() === 'PATH') ?? 'PATH'

/** PAPERLAB_DOCKER, then each folder on PATH, then the fixed places: apps started from Finder or the Start menu don't
 * get the shell's PATH. null: no docker. */
export function findDocker(
  platform: NodeJS.Platform,
  env: NodeJS.ProcessEnv,
  home: string,
  isUsable: (path: string) => boolean,
): string | null {
  const path = platform === 'win32' ? win32 : posix
  const exe = platform === 'win32' ? 'docker.exe' : 'docker'
  const onPath = (env[pathKey(env)] ?? '').split(path.delimiter).filter(Boolean).map((dir) => path.join(dir, exe))
  const candidates = [env.PAPERLAB_DOCKER ?? '', ...onPath, ...fallbackPaths(platform, env, home)]
  return candidates.find((candidate) => candidate !== '' && isUsable(candidate)) ?? null
}

/** A file this user may run (on Windows, one that exists). */
export function usable(path: string): boolean {
  try {
    accessSync(path, constants.X_OK)
    return statSync(path).isFile()
  } catch {
    return false // not there, or not runnable: try the next place
  }
}

/** Docker Desktop's own CLI, which the app may start when Docker isn't running. Any other Docker is left alone. */
export function isDockerDesktop(realPath: string, platform: NodeJS.Platform): boolean {
  if (platform === 'darwin') return realPath.includes('/Docker.app/')
  if (platform === 'win32') return realPath.toLowerCase().includes('\\docker\\docker\\resources\\bin\\')
  return false
}

/** The found docker's folder first on PATH, so the credential helper beside it is found during a pull, and the three
 * variables the compose file reads. */
export function commandEnv(docker: string, base: NodeJS.ProcessEnv, stack: StackInfo, platform: NodeJS.Platform): NodeJS.ProcessEnv {
  const path = platform === 'win32' ? win32 : posix
  const key = pathKey(base)
  return {
    ...base,
    [key]: [path.dirname(docker), base[key]].filter(Boolean).join(path.delimiter),
    PAPERLAB_VERSION: stack.version,
    PAPERLAB_DIR: stack.dataDir,
    PAPERLAB_PORT: String(stack.port),
  }
}

/** Compose 2.24 or later: the compose file's env_file is optional only from then. */
export function composeVersionOk(result: Result): boolean {
  const found = result.code === 0 && !result.timedOut ? /v?(\d+)\.(\d+)/.exec(result.stdout) : null
  if (found === null) return false
  const [major, minor] = [Number(found[1]), Number(found[2])]
  return major > 2 || (major === 2 && minor >= 24)
}

/** The last non-empty line of a command's error output, else of its output. */
export function lastLine(result: Pick<Result, 'stdout' | 'stderr'>): string | null {
  const last = (text: string) =>
    text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .at(-1) ?? null
  return last(result.stderr) ?? last(result.stdout)
}

/** Local image tags older than this version. A tag that isn't a version (dev) stays. */
export function staleTags(tags: readonly string[], current: string): string[] {
  return tags.map((tag) => tag.trim()).filter((tag) => (compareVersions(tag, current) ?? 0) < 0)
}

/** Keeps memory flat during a pull, which has no time limit and can print progress for minutes: only this many
 * trailing characters of stdout/stderr are kept. onLine still sees every line as it streams by. */
const OUTPUT_TAIL = 16 * 1024

/** Ends a timed-out command's whole process tree, not just the immediate child: `docker compose` runs the compose
 * plugin as its own child process, which plain `child.kill()` leaves running.
 * POSIX: spawnRunner starts the command as its own process-group leader, so `-pid` signals the whole group; a group
 * that can't be signalled that way falls back to killing just the child.
 * Windows has no process groups, so `taskkill /T` walks the same parent-child tree instead; it's fire-and-forget,
 * with any failure only logged. */
function killTree(child: ChildProcess): void {
  if (process.platform === 'win32') {
    if (child.pid !== undefined) {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { shell: false, windowsHide: true }).on('error', (error) => {
        console.error('PaperLab could not stop a timed-out docker command', error)
      })
    }
    return
  }
  try {
    if (child.pid !== undefined) process.kill(-child.pid, 'SIGTERM')
  } catch {
    child.kill()
  }
}

/** Runs a command without a shell (a data folder with spaces stays one argument), ends it and everything it spawned
 * past its time limit, and hands each output line to onLine as it arrives. */
export const spawnRunner: Runner = (file, args, { env, timeoutMs, onLine, signal }) =>
  new Promise((resolve) => {
    const child = spawn(file, args, { env, shell: false, windowsHide: true, signal, detached: process.platform !== 'win32' })
    const output = { stdout: '', stderr: '' }
    let timedOut = false
    const expire = () => {
      timedOut = true
      killTree(child)
    }
    const timer = timeoutMs === null ? null : setTimeout(expire, timeoutMs)
    const collect = (stream: 'stdout' | 'stderr') => (chunk: Buffer) => {
      const text = chunk.toString()
      output[stream] = (output[stream] + text).slice(-OUTPUT_TAIL)
      for (const line of text.split(/\r?\n|\r/)) if (line.trim()) onLine?.(line.trim())
    }
    child.stdout.on('data', collect('stdout'))
    child.stderr.on('data', collect('stderr'))
    const finish = (code: number, error = '') => {
      if (timer !== null) clearTimeout(timer)
      // The window closing during startup aborts `signal`: Node's own handling for it kills only this immediate
      // child (then emits 'error' here, before a listener added on `signal` afterwards would run), which leaves
      // `docker compose`'s own child process (the compose plugin) running, same as a plain child.kill() would.
      // killTree ends the whole tree instead, exactly as the timeout path above already does.
      if (signal?.aborted === true) killTree(child)
      resolve({ code, stdout: output.stdout, stderr: output.stderr + error, timedOut })
    }
    child.on('error', (error) => finish(-1, String(error)))
    child.on('close', (code) => finish(code ?? -1))
  })

/** pg_dump of the library, gzipped straight into `path` (D142): the dump streams to the file, never into memory. No
 * time limit, like a pull: a large library takes a while. */
async function dumpTo(bin: string, args: string[], env: NodeJS.ProcessEnv, path: string, log: Log): Promise<Result> {
  const child = spawn(bin, args, { env, shell: false, windowsHide: true })
  const errors: string[] = []
  child.stderr.on('data', (chunk: Buffer) => {
    errors.push(chunk.toString())
  })
  const exited = new Promise<number>((resolve) => {
    child.on('error', (error) => {
      errors.push(String(error))
      resolve(-1)
    })
    child.on('close', (code) => resolve(code ?? -1))
  })
  const written = pipeline(child.stdout, createGzip(), createWriteStream(path)).then(
    () => null,
    (error: unknown) => String(error),
  )
  const [exitCode, writeError] = await Promise.all([exited, written])
  // A dump that couldn't be written (disk full) fails even when pg_dump itself finished.
  const code = writeError === null ? exitCode : exitCode || 1
  const stderr = [...errors, ...(writeError === null ? [] : [`\n${writeError}`])].join('')
  log(`docker ${args.join(' ')} → exit ${code}`)
  return { code, stdout: '', stderr, timedOut: false }
}

export type DockerOptions = { platform?: NodeJS.Platform; env?: NodeJS.ProcessEnv; signal?: AbortSignal }

/** The docker commands the launch runs, each logged with its exit code. `signal` ends a running one (the window closed
 * during startup); stop() never takes it, since it runs after. */
export function makeDocker(bin: string, run: Runner, stack: StackInfo, log: Log, options: DockerOptions = {}) {
  const env = commandEnv(bin, options.env ?? process.env, stack, options.platform ?? process.platform)
  const file = join(stack.dataDir, 'docker-compose.yml')
  const docker = async (args: string[], timeoutMs: number | null, onLine?: (line: string) => void, abortable = true) => {
    const result = await run(bin, args, { env, timeoutMs, onLine, signal: abortable ? options.signal : undefined })
    log(`docker ${args.join(' ')} → ${result.timedOut ? 'timed out' : `exit ${result.code}`}`)
    return result
  }
  const compose = (args: string[], timeoutMs: number | null, onLine?: (line: string) => void, abortable = true) =>
    docker(['compose', '-f', file, ...args], timeoutMs, onLine, abortable)
  return {
    info: () => docker(['info', '--format', '{{.OSType}}'], LIMITS.info),
    composeVersion: () => docker(['compose', 'version', '--short'], LIMITS.version),
    imagePresent: async () => (await docker(['image', 'inspect', `${IMAGE}:${stack.version}`], LIMITS.info)).code === 0,
    pull: (onLine: (line: string) => void) => compose(['pull'], LIMITS.pull, onLine),
    startDatabase: () => compose(['up', '-d', '--wait', 'db'], LIMITS.up),
    up: () => compose(['up', '-d'], LIMITS.up),
    logs: (services: string[]) => compose(['logs', '--no-color', '--tail', '20', ...services], LIMITS.info),
    stop: () => compose(['stop'], LIMITS.stop, undefined, false),
    imageTags: () => docker(['image', 'ls', IMAGE, '--format', '{{.Tag}}'], LIMITS.info),
    removeImage: (tag: string) => docker(['image', 'rm', `${IMAGE}:${tag}`], LIMITS.info),
    dumpTo: (path: string) =>
      dumpTo(bin, ['compose', '-f', file, 'exec', '-T', 'db', 'pg_dump', '-U', 'paperlab', 'paperlab'], env, path, log),
  }
}

export type Docker = ReturnType<typeof makeDocker>
