type Options = {
  threshold: number
  /** How long the voice must stay at or above `threshold`. */
  sustainMs: number
  frameMs: number
  /** Called once per interruption with the time of the first voiced frame. */
  onTrigger: (startedAt: number) => void
}

/** Decides that the reader is talking over the answer: a sustained run of voiced frames while it plays. */
export function createInterruptDetector({ threshold, sustainMs, frameMs, onTrigger }: Options) {
  let runMs = 0
  let startedAt = 0
  return {
    frame(probability: number, playing: boolean, now: number) {
      if (!playing || probability < threshold) {
        runMs = 0
        return
      }
      if (runMs === 0) startedAt = now
      runMs += frameMs
      if (runMs >= sustainMs) {
        runMs = 0
        onTrigger(startedAt)
      }
    },
  }
}
