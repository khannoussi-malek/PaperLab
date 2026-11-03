// Tuned on real speakers and microphones by the voice demo; change them only with a new measurement.
export const FRAME_MS = 32 // one Silero v5 frame: 512 samples at 16 kHz
export const SILENCE_MS = 800 // how long a pause ends the question
export const SPEECH_THRESHOLD = 0.5
export const NEGATIVE_THRESHOLD = 0.35
export const INTERRUPT_THRESHOLD = 0.7 // stricter while the app is talking
export const INTERRUPT_SUSTAIN_MS = 250
export const PRE_SPEECH_PAD_MS = 300
export const MIN_SPEECH_MS = 250
export const PLAY_LEAD_S = 0.05 // slack before the first chunk starts, so it is never scheduled in the past
export const VAD_MODEL = 'v5'
/** Where `copy-voice-assets.mjs` puts the speech detector's model, worklet and wasm. */
export const VOICE_ASSETS = '/voice/'
/** The API's limit: a minute of 16 kHz float32. */
export const MAX_UTTERANCE_BYTES = 16000 * 4 * 60
