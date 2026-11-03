import { PLAY_LEAD_S } from './constants'

export type Playback = {
  /** Queues a chunk after the ones before it; `onFirst` gets the `performance.now()` time it will be heard. */
  play(samples: Float32Array, rate: number, onFirst?: (playedAt: number) => void): void
  /** Silences everything queued and forgets it. */
  stop(): void
  active(): boolean
  /** Seconds of the queue that have been heard so far. */
  playedSeconds(): number
}

/**
 * Plays streamed audio chunks back to back through `out`. `onIdle` runs when the last queued chunk ends by itself;
 * `stop` does not call it.
 */
export function createPlayback(ctx: AudioContext, out: AudioNode, onIdle?: () => void): Playback {
  let head = 0 // when the queue ends, in the context's time
  const live = new Set<AudioBufferSourceNode>()
  let scheduled: { at: number; duration: number }[] = []

  return {
    play(samples, rate, onFirst) {
      const buffer = ctx.createBuffer(1, samples.length, rate)
      buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0)
      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.connect(out)
      const at = Math.max(head, ctx.currentTime + PLAY_LEAD_S)
      source.start(at)
      head = at + buffer.duration
      live.add(source)
      source.onended = () => {
        live.delete(source)
        if (live.size === 0) onIdle?.()
      }
      scheduled = [...scheduled, { at, duration: buffer.duration }]
      onFirst?.(performance.now() + (at - ctx.currentTime) * 1000)
    },
    stop() {
      live.forEach((source) => {
        source.onended = null
        source.stop()
      })
      live.clear()
      scheduled = []
      head = 0
    },
    active: () => live.size > 0,
    playedSeconds: () =>
      scheduled.reduce((sum, { at, duration }) => sum + Math.min(Math.max(ctx.currentTime - at, 0), duration), 0),
  }
}
