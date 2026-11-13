/**
 * Settings → Voice in the desktop app: turning the voice container on or off, and removing its models. Pure over a
 * Docker object, so main.ts only wires the IPC and these rules stay testable.
 */
import { lastLine, type Docker, type Result } from './docker'

export type VoiceDocker = Pick<Docker, 'voiceOn' | 'voiceOff' | 'removeVoiceModels' | 'voiceOutOfMemory'>
export type VoiceReply = { ok: boolean; detail: string | null }

export const NO_DOCKER = 'Docker was not found.'
export const VOICE_ON_FIRST = 'Turn voice off first.'
export const BUSY = 'Voice is still changing. Wait a moment.'

let busy = false

/** One change at a time: a set or a model removal that comes while another runs is refused, so an off pressed during
 * an on's pull never races it. */
export async function withVoiceLock(change: () => Promise<VoiceReply>): Promise<VoiceReply> {
  if (busy) return { ok: false, detail: BUSY }
  busy = true
  try {
    return await change()
  } finally {
    busy = false
  }
}

const succeeded = (result: Result) => result.code === 0 && !result.timedOut

/** The last line of the command's own output, else a plain fallback. */
const failure = (result: Result, fallback: string): VoiceReply => ({ ok: false, detail: lastLine(result) ?? fallback })

/** Turns voice on (progress to onLine) or off. The setting is saved only when the change worked, so a failed turn-off
 * leaves it on: the container may still be running, and the next launch would not stop it. */
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
    if (!succeeded(off)) return failure(off, 'Voice could not be turned off.')
    save(false)
    return { ok: true, detail: null }
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

/** Starts the voice service after PaperLab is up, when voice is on. Not awaited by the launch: a voice problem is logged
 * and never fails or delays the app. */
export async function startVoiceIfOn(
  settings: { voiceEnabled: boolean },
  docker: Pick<Docker, 'voiceStart'>,
  log: (line: string) => void,
): Promise<void> {
  if (!settings.voiceEnabled) return
  try {
    const started = await docker.voiceStart()
    if (!succeeded(started)) log(`voice did not start: ${lastLine(started) ?? `exit ${started.code}`}`)
  } catch (error) {
    log(`voice did not start: ${String(error)}`)
  }
}
