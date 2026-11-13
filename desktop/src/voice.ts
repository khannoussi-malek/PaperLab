/**
 * Settings → Voice in the desktop app: turning the voice container on or off, and removing its models. Pure over a
 * Docker object, so main.ts only wires the IPC and these rules stay testable.
 */
import { lastLine, type Docker, type Result } from './docker'

export type VoiceDocker = Pick<Docker, 'voiceOn' | 'voiceOff' | 'removeVoiceModels' | 'voiceOutOfMemory'>
export type VoiceReply = { ok: boolean; detail: string | null }

export const NO_DOCKER = 'Docker was not found.'
export const VOICE_ON_FIRST = 'Turn voice off first.'

const succeeded = (result: Result) => result.code === 0 && !result.timedOut

/** The last line of the command's own output, else a plain fallback. */
const failure = (result: Result, fallback: string): VoiceReply => ({ ok: false, detail: lastLine(result) ?? fallback })

/** Turns voice on (progress to onLine) or off. The setting is saved only when turning on worked; turning off always
 * saves off, so the switch never reads on while the container was asked to stop. */
export async function setVoice(
  docker: VoiceDocker | null,
  value: boolean,
  onLine: (line: string) => void,
  save: (value: boolean) => void,
): Promise<VoiceReply> {
  if (docker === null) {
    if (!value) save(false)
    return { ok: false, detail: NO_DOCKER }
  }
  if (!value) {
    const off = await docker.voiceOff()
    save(false)
    return succeeded(off) ? { ok: true, detail: null } : failure(off, 'Voice could not be turned off.')
  }
  const on = await docker.voiceOn(onLine)
  if (!succeeded(on)) return failure(on, 'Voice could not be turned on.')
  save(true)
  return { ok: true, detail: null }
}

/** The models are only removed while voice is off (the container would be holding them). */
export async function removeModels(docker: VoiceDocker | null, voiceIsOn: boolean): Promise<VoiceReply> {
  if (voiceIsOn) return { ok: false, detail: VOICE_ON_FIRST }
  if (docker === null) return { ok: false, detail: NO_DOCKER }
  const removed = await docker.removeVoiceModels()
  return succeeded(removed) ? { ok: true, detail: null } : failure(removed, 'The voice models could not be removed.')
}
