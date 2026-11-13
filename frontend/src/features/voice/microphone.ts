import {
  MIN_SPEECH_MS,
  NEGATIVE_THRESHOLD,
  PRE_SPEECH_PAD_MS,
  SILENCE_MS,
  SPEECH_THRESHOLD,
  VAD_MODEL,
  VOICE_ASSETS,
} from './constants'

export type MicrophoneHandlers = {
  /** Every 32 ms frame's chance of being speech, 0 to 1. */
  onFrame: (probability: number) => void
  onSpeechStart: () => void
  /** The finished utterance: 16 kHz mono float32. */
  onSpeechEnd: (audio: Float32Array) => void
  /** The track died (unplugged, revoked): nothing more will be heard. */
  onEnded: () => void
  /** The track is open but sending silence, and when sound returns. */
  onMuted: () => void
  onUnmuted: () => void
}

export type Microphone = {
  stop: () => Promise<void>
  /** False when the browser did not turn echo cancelling on; the app would then hear its own voice. */
  echoCancelled: boolean
}

/** A reason in words, for the reader. */
export class MicrophoneError extends Error {}

function describe(error: unknown): string {
  const name = error instanceof DOMException ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone access was refused. You can allow it in your system settings.'
  }
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'No microphone was found.'
  if (name === 'NotReadableError') return 'The microphone is in use by another app.'
  return 'The microphone could not be started.'
}

/**
 * Opens the microphone and starts listening for questions. The speech detector (a model and a wasm runtime) loads
 * here, on first use, so the app's first load doesn't carry it. Rejects with a MicrophoneError.
 */
export async function startMicrophone(handlers: MicrophoneHandlers): Promise<Microphone> {
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
    })
  } catch (error) {
    throw new MicrophoneError(describe(error))
  }
  const track = stream.getAudioTracks()[0]
  const release = () => stream.getTracks().forEach((t) => t.stop())
  const watched = [
    ['ended', handlers.onEnded],
    ['mute', handlers.onMuted],
    ['unmute', handlers.onUnmuted],
  ] as const
  for (const [event, listener] of watched) track.addEventListener(event, listener)
  const unwatch = () => watched.forEach(([event, listener]) => track.removeEventListener(event, listener))
  try {
    const { MicVAD } = await import('@ricky0123/vad-web')
    const vad = await MicVAD.new({
      model: VAD_MODEL,
      startOnLoad: true,
      baseAssetPath: VOICE_ASSETS,
      // Absolute on purpose: the runtime imports its wasm loader from here, and Vite's dev server turns a root-relative
      // dynamic import into "?import" and then refuses it as a public file.
      onnxWASMBasePath: `${location.origin}${VOICE_ASSETS}`,
      positiveSpeechThreshold: SPEECH_THRESHOLD,
      negativeSpeechThreshold: NEGATIVE_THRESHOLD,
      redemptionMs: SILENCE_MS,
      preSpeechPadMs: PRE_SPEECH_PAD_MS,
      minSpeechMs: MIN_SPEECH_MS,
      getStream: async () => stream,
      onFrameProcessed: ({ isSpeech }) => handlers.onFrame(isSpeech),
      onSpeechStart: handlers.onSpeechStart,
      onSpeechEnd: handlers.onSpeechEnd,
    })
    return {
      echoCancelled: track.getSettings().echoCancellation !== false,
      stop: async () => {
        unwatch()
        try {
          await vad.destroy()
        } finally {
          release()
        }
      },
    }
  } catch (error) {
    console.warn('the speech detector did not start', error)
    unwatch()
    release()
    throw new MicrophoneError(describe(null))
  }
}
