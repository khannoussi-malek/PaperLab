import { describe, expect, it } from 'vitest'
import type { Result } from './docker'
import { removeModels, setVoice, type VoiceDocker } from './voice'

const result = (more: Partial<Result> = {}): Result => ({ code: 0, stdout: '', stderr: '', timedOut: false, ...more })

function fakeDocker(answers: { on?: Result; off?: Result; remove?: Result } = {}) {
  const calls: string[] = []
  const docker: VoiceDocker = {
    voiceOn: async (onLine) => {
      calls.push('on')
      onLine('pulling the voice image')
      return answers.on ?? result()
    },
    voiceOff: async () => {
      calls.push('off')
      return answers.off ?? result()
    },
    removeVoiceModels: async () => {
      calls.push('remove')
      return answers.remove ?? result()
    },
    voiceOutOfMemory: async () => false,
  }
  return { docker, calls }
}

describe('setVoice', () => {
  it('turns voice on, passes each progress line on, and saves the setting only then', async () => {
    const { docker, calls } = fakeDocker()
    const lines: string[] = []
    const saved: boolean[] = []

    const reply = await setVoice(docker, true, (line) => lines.push(line), (value) => saved.push(value))

    expect(reply).toEqual({ ok: true, detail: null })
    expect(calls).toEqual(['on'])
    expect(lines).toEqual(['pulling the voice image'])
    expect(saved).toEqual([true])
  })

  it('a failed turn-on saves nothing and says the last line of the error', async () => {
    const { docker } = fakeDocker({ on: result({ code: 1, stderr: 'pulling\nno space left on device\n' }) })
    const saved: boolean[] = []

    const reply = await setVoice(docker, true, () => {}, (value) => saved.push(value))

    expect(reply).toEqual({ ok: false, detail: 'no space left on device' })
    expect(saved).toEqual([])
  })

  it('turns voice off by stopping and removing the container, then saves off', async () => {
    const { docker, calls } = fakeDocker()
    const saved: boolean[] = []

    const reply = await setVoice(docker, false, () => {}, (value) => saved.push(value))

    expect(reply).toEqual({ ok: true, detail: null })
    expect(calls).toEqual(['off'])
    expect(saved).toEqual([false])
  })

  it('a failed turn-off still saves off, so the switch reads off, and reports the failure', async () => {
    const { docker } = fakeDocker({ off: result({ code: 1, stderr: 'daemon gone\n' }) })
    const saved: boolean[] = []

    const reply = await setVoice(docker, false, () => {}, (value) => saved.push(value))

    expect(reply).toEqual({ ok: false, detail: 'daemon gone' })
    expect(saved).toEqual([false])
  })

  it('without Docker, turning on fails with a plain reason, and turning off still saves off', async () => {
    const saved: boolean[] = []

    expect(await setVoice(null, true, () => {}, (value) => saved.push(value))).toEqual({ ok: false, detail: 'Docker was not found.' })
    expect(saved).toEqual([])
    await setVoice(null, false, () => {}, (value) => saved.push(value))
    expect(saved).toEqual([false])
  })
})

describe('removeModels', () => {
  it('refuses while voice is on, and does not touch Docker', async () => {
    const { docker, calls } = fakeDocker()

    expect(await removeModels(docker, true)).toEqual({ ok: false, detail: 'Turn voice off first.' })
    expect(calls).toEqual([])
  })

  it('removes the models once voice is off', async () => {
    const { docker, calls } = fakeDocker()

    expect(await removeModels(docker, false)).toEqual({ ok: true, detail: null })
    expect(calls).toEqual(['remove'])
  })

  it('says why the removal failed, or gives a plain fallback when Docker said nothing', async () => {
    const failing = fakeDocker({ remove: result({ code: 1, stderr: 'volume is in use\n' }) }).docker
    const silent = fakeDocker({ remove: result({ code: 1 }) }).docker

    expect(await removeModels(failing, false)).toEqual({ ok: false, detail: 'volume is in use' })
    expect(await removeModels(silent, false)).toEqual({ ok: false, detail: 'The voice models could not be removed.' })
    expect(await removeModels(null, false)).toEqual({ ok: false, detail: 'Docker was not found.' })
  })
})
