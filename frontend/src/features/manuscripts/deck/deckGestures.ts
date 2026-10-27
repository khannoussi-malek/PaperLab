/** Hand gestures as deck actions. Pure: each step takes the running totals and returns the new ones plus what to do. */
export type DeckAction = { type: 'step'; by: 1 | -1 } | { type: 'open' } | { type: 'close' }
export type GestureTotals = { turn: number; zoom: number }

export const TURN_PER_CARD = 0.35
export const OPEN_ABOVE = 1.25
export const CLOSE_BELOW = 0.8
export const initialTotals: GestureTotals = { turn: 0, zoom: 1 }

/** A two-finger flick is one step. */
export const hopAction = (step: 1 | -1): DeckAction => ({ type: 'step', by: step })

/** An open hand gliding sideways: one card per TURN_PER_CARD radians, the remainder kept. */
export function turnStep(t: GestureTotals, azimuth: number): [GestureTotals, DeckAction | null] {
  const turn = t.turn + azimuth
  if (Math.abs(turn) < TURN_PER_CARD) return [{ ...t, turn }, null]
  const by = turn > 0 ? 1 : -1
  return [{ ...t, turn: turn - by * TURN_PER_CARD }, { type: 'step', by }]
}

/** Two hands: spreading past OPEN_ABOVE opens the paper, bringing together past CLOSE_BELOW shuts it. */
export function zoomStep(t: GestureTotals, factor: number): [GestureTotals, DeckAction | null] {
  const zoom = t.zoom * factor
  if (zoom > OPEN_ABOVE) return [{ ...t, zoom: 1 }, { type: 'open' }]
  if (zoom < CLOSE_BELOW) return [{ ...t, zoom: 1 }, { type: 'close' }]
  return [{ ...t, zoom }, null]
}
