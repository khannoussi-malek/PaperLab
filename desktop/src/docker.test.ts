import { randomUUID } from 'node:crypto'
import { readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  commandEnv,
  composeVersionOk,
  fallbackPaths,
  findDocker,
  IMAGE,
  isDockerDesktop,
  lastLine,
  makeDocker,
  spawnRunner,
  staleTags,
  type Result,
  type Runner,
  type RunOptions,
} from './docker'

const HOME = '/Users/reader'
const STACK = { dataDir: '/data/PaperLab data', version: '0.1.0', port: 5190 }
const result = (more: Partial<Result> = {}): Result => ({ code: 0, stdout: '', stderr: '', timedOut: false, ...more })
const only = (...paths: string[]) => (path: string) => paths.includes(path)

describe('findDocker', () => {
  it('takes PAPERLAB_DOCKER first, then PATH, then the fixed places, else none', () => {
    const everywhere = only('/opt/custom/docker', '/usr/bin/docker', '/usr/local/bin/docker')

    expect(findDocker('darwin', { PAPERLAB_DOCKER: '/opt/custom/docker', PATH: '/usr/bin:/bin' }, HOME, everywhere)).toBe(
      '/opt/custom/docker',
    )
    expect(findDocker('darwin', { PATH: '/usr/bin:/bin' }, HOME, everywhere)).toBe('/usr/bin/docker')
    expect(findDocker('darwin', { PATH: '/bin' }, HOME, everywhere)).toBe('/usr/local/bin/docker')
    expect(findDocker('darwin', { PATH: '/bin' }, HOME, only(`${HOME}/.docker/bin/docker`))).toBe(`${HOME}/.docker/bin/docker`)
    expect(findDocker('darwin', { PATH: '/bin' }, HOME, only())).toBeNull()
  })

  it("goes on past a PAPERLAB_DOCKER that isn't there", () => {
    const env = { PAPERLAB_DOCKER: '/gone/docker', PATH: '/bin' }

    expect(findDocker('darwin', env, HOME, only('/usr/local/bin/docker'))).toBe('/usr/local/bin/docker')
  })

  it("reads Windows' Path (semicolons, docker.exe) and knows where Docker Desktop installs it", () => {
    const desktop = 'C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe'
    const env = { Path: 'C:\\Windows;C:\\tools', ProgramFiles: 'C:\\Program Files' }

    expect(findDocker('win32', env, 'C:\\Users\\reader', only('C:\\tools\\docker.exe', desktop))).toBe('C:\\tools\\docker.exe')
    expect(findDocker('win32', env, 'C:\\Users\\reader', only(desktop))).toBe(desktop)
  })
})

describe('fallbackPaths', () => {
  it("is scripts/paperlab-mcp's list, in the same order", () => {
    const script = readFileSync(resolve('..', 'scripts', 'paperlab-mcp'), 'utf8')
    const listed = /fallback_paths="([^"]+)"/.exec(script)?.[1] ?? ''

    expect(fallbackPaths('darwin', {}, HOME)).toEqual(listed.replaceAll('${HOME:-}', HOME).split(' '))
    expect(fallbackPaths('darwin', {}, HOME).slice(0, 2)).toEqual([`${HOME}/.docker/bin/docker`, `${HOME}/.rd/bin/docker`])
  })

  it('takes PAPERLAB_DOCKER_PATHS instead, as the script does, and none when it is empty', () => {
    expect(fallbackPaths('darwin', { PAPERLAB_DOCKER_PATHS: '/a/docker /b/docker' }, HOME)).toEqual(['/a/docker', '/b/docker'])
    expect(fallbackPaths('linux', { PAPERLAB_DOCKER_PATHS: '' }, HOME)).toEqual([])
  })
})

describe('commandEnv', () => {
  it("puts the found docker's folder first on PATH, so its credential helper is found, and sets PaperLab's three variables", () => {
    const docker = '/Applications/Docker.app/Contents/Resources/bin/docker'

    expect(commandEnv(docker, { PATH: '/usr/bin:/bin', HOME }, STACK, 'darwin')).toEqual({
      PATH: '/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin',
      HOME,
      PAPERLAB_VERSION: '0.1.0',
      PAPERLAB_DIR: '/data/PaperLab data',
      PAPERLAB_PORT: '5190',
    })
  })

  it("keeps Windows' own Path key rather than adding a second one", () => {
    const env = commandEnv('C:\\Docker\\docker.exe', { Path: 'C:\\Windows' }, STACK, 'win32')

    expect(env.Path).toBe('C:\\Docker;C:\\Windows')
    expect(env.PATH).toBeUndefined()
  })
})

describe('checks on what docker answers', () => {
  it('accepts Compose 2.24 and later, and refuses 2.23, a missing plugin and a timeout', () => {
    expect(composeVersionOk(result({ stdout: '2.23.3\n' }))).toBe(false)
    expect(composeVersionOk(result({ stdout: '2.24.0\n' }))).toBe(true)
    expect(composeVersionOk(result({ stdout: 'v2.29.1-desktop.1\n' }))).toBe(true)
    expect(composeVersionOk(result({ stdout: '3.0.0\n' }))).toBe(true)
    expect(composeVersionOk(result({ code: 1, stderr: "docker: 'compose' is not a docker command.\n" }))).toBe(false)
    expect(composeVersionOk(result({ stdout: '2.29.1\n', timedOut: true }))).toBe(false)
  })

  it('tells Docker Desktop from any other Docker by where its binary really is', () => {
    expect(isDockerDesktop('/Applications/Docker.app/Contents/Resources/bin/docker', 'darwin')).toBe(true)
    expect(isDockerDesktop('/opt/homebrew/Cellar/docker/28.0.0/bin/docker', 'darwin')).toBe(false)
    expect(isDockerDesktop('C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe', 'win32')).toBe(true)
    expect(isDockerDesktop('/usr/bin/docker', 'linux')).toBe(false)
  })

  it("keeps only the old versions' images, never a tag that isn't a version", () => {
    expect(staleTags(['0.1.0', '0.0.9\n', 'dev', '0.2.0', '<none>', '0.1.0-rc.1'], '0.1.0')).toEqual(['0.0.9', '0.1.0-rc.1'])
  })

  it('names the last line of the error output, else of the output', () => {
    expect(lastLine(result({ stdout: 'a\n', stderr: 'b\nc\n\n' }))).toBe('c')
    expect(lastLine(result({ stdout: 'a\nb\n' }))).toBe('b')
    expect(lastLine(result())).toBeNull()
  })
})

describe('spawnRunner', () => {
  it('passes a folder with spaces as one argument, with no shell, and hands each output line on', async () => {
    const lines: string[] = []
    const script = 'console.log(JSON.stringify(process.argv.slice(1))); console.error("second line")'
    const options: RunOptions = { env: process.env, timeoutMs: 10_000, onLine: (line) => void lines.push(line) }

    const ran = await spawnRunner(process.execPath, ['-e', script, '/data/PaperLab data'], options)

    expect(ran).toMatchObject({ code: 0, timedOut: false })
    expect(JSON.parse(ran.stdout)).toEqual(['/data/PaperLab data'])
    expect(lines.toSorted()).toEqual(['["/data/PaperLab data"]', 'second line'])
  })

  it('ends a command past its time limit, and says so', async () => {
    const started = Date.now()

    const ran = await spawnRunner(process.execPath, ['-e', 'setTimeout(() => {}, 30_000)'], { env: process.env, timeoutMs: 300 })

    expect(ran.timedOut).toBe(true)
    expect(Date.now() - started).toBeLessThan(5_000)
  })

  it.skipIf(process.platform === 'win32')("ends a timed-out command's grandchild too, not just its immediate child", async () => {
    const pidFile = join(tmpdir(), `paperlab-docker-test-${randomUUID()}.pid`)
    const script = [
      "const { spawn } = require('node:child_process')",
      "const fs = require('node:fs')",
      "const grandchild = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)'])",
      `fs.writeFileSync(${JSON.stringify(pidFile)}, String(grandchild.pid))`,
      'setTimeout(() => {}, 30000)',
    ].join('; ')

    try {
      const ran = await spawnRunner(process.execPath, ['-e', script], { env: process.env, timeoutMs: 300 })
      expect(ran.timedOut).toBe(true)

      const grandchildPid = Number(readFileSync(pidFile, 'utf8'))
      await new Promise((r) => setTimeout(r, 500))
      expect(() => process.kill(grandchildPid, 0)).toThrow(/ESRCH/)
    } finally {
      rmSync(pidFile, { force: true })
    }
  })

  it.skipIf(process.platform === 'win32')("ends an aborted command's grandchild too, not just its immediate child", async () => {
    const pidFile = join(tmpdir(), `paperlab-docker-test-${randomUUID()}.pid`)
    const script = [
      "const { spawn } = require('node:child_process')",
      "const fs = require('node:fs')",
      "const grandchild = spawn(process.execPath, ['-e', 'setTimeout(() => {}, 30000)'])",
      `fs.writeFileSync(${JSON.stringify(pidFile)}, String(grandchild.pid))`,
      'setTimeout(() => {}, 30000)',
    ].join('; ')
    const ac = new AbortController()

    try {
      const ran = spawnRunner(process.execPath, ['-e', script], { env: process.env, timeoutMs: 10_000, signal: ac.signal })
      await new Promise((r) => setTimeout(r, 300))
      ac.abort()
      await ran

      const grandchildPid = Number(readFileSync(pidFile, 'utf8'))
      await new Promise((r) => setTimeout(r, 500))
      expect(() => process.kill(grandchildPid, 0)).toThrow(/ESRCH/)
    } finally {
      rmSync(pidFile, { force: true })
    }
  })

  it('keeps only a bounded tail of a long-running command\'s output, ending in the final line', async () => {
    const script = "for (let i = 0; i < 20000; i++) process.stdout.write('x'.repeat(50) + '\\n'); console.log('THE FINAL LINE')"

    const ran = await spawnRunner(process.execPath, ['-e', script], { env: process.env, timeoutMs: 10_000 })

    expect(ran.stdout.length).toBeLessThanOrEqual(16 * 1024)
    expect(ran.stdout.trimEnd().endsWith('THE FINAL LINE')).toBe(true)
    expect(lastLine(ran)).toBe('THE FINAL LINE')
  })
})

describe('makeDocker', () => {
  function recorded(answer: (args: readonly string[]) => Partial<Result> = () => ({})) {
    const calls: Array<{ args: string; timeoutMs: number | null; env: NodeJS.ProcessEnv; signal?: AbortSignal }> = []
    const run: Runner = async (_file, args, options) => {
      calls.push({ args: args.join(' '), timeoutMs: options.timeoutMs, env: options.env, signal: options.signal })
      return result(answer(args))
    }
    return { run, calls }
  }

  it("runs compose on the data folder's file with a time limit each, and logs every command with its exit code", async () => {
    const { run, calls } = recorded((args) => ({ code: args.includes('inspect') ? 1 : 0 }))
    const lines: string[] = []
    const closing = new AbortController()
    const docker = makeDocker('/usr/local/bin/docker', run, STACK, (line) => void lines.push(line), {
      platform: 'darwin',
      env: { PATH: '/bin' },
      signal: closing.signal,
    })

    await docker.up()
    await docker.stop()
    expect(await docker.imagePresent()).toBe(false)

    const file = '/data/PaperLab data/docker-compose.yml'
    expect(calls.map(({ args, timeoutMs }) => [args, timeoutMs])).toEqual([
      [`compose -f ${file} up -d`, 300_000],
      [`compose -f ${file} stop`, 30_000],
      [`image inspect ${IMAGE}:0.1.0`, 15_000],
    ])
    expect(calls[0].env.PAPERLAB_DIR).toBe('/data/PaperLab data')
    expect(calls[0].signal).toBe(closing.signal)
    expect(calls[1].signal).toBeUndefined() // stop runs after a close has ended the launch
    expect(lines).toEqual([
      `docker compose -f ${file} up -d → exit 0`,
      `docker compose -f ${file} stop → exit 0`,
      `docker image inspect ${IMAGE}:0.1.0 → exit 1`,
    ])
  })

  it('pulls with no time limit, handing on each progress line, and starts the database alone and waits for it', async () => {
    const { run, calls } = recorded()
    const progress: string[] = []
    const docker = makeDocker('/usr/local/bin/docker', run, STACK, () => {}, { platform: 'darwin', env: {} })

    await docker.pull((line) => void progress.push(line))
    await docker.startDatabase()

    expect(calls.map(({ args, timeoutMs }) => [args.replace(/^compose -f \S+ \S+ /, 'compose '), timeoutMs])).toEqual([
      ['compose pull', null],
      ['compose up -d --wait db', 300_000],
    ])
  })
})
