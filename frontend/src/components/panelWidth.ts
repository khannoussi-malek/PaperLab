/**
 * A panel the user can drag wider or narrower, and the app remembers. Every panel brings its own limits, so the
 * reader's Notes/Chat panel and the Charts preview share this code without sharing a width.
 */
export type PanelLimits = {
  /** Where this panel's chosen width is remembered. One key per panel. */
  storageKey: string
  defaultWidth: number
  minWidth: number
  /** The panel takes at most this share of the window, so what it sits beside always keeps the larger part. */
  maxShare: number
}

type WidthStorage = Pick<Storage, 'getItem' | 'setItem'>

export const maxPanelWidth = (limits: PanelLimits, viewportWidth: number) =>
  Math.max(limits.minWidth, Math.floor(viewportWidth * limits.maxShare))

export function clampPanelWidth(limits: PanelLimits, width: number, viewportWidth: number): number {
  if (!Number.isFinite(width)) return limits.defaultWidth
  return Math.min(maxPanelWidth(limits, viewportWidth), Math.max(limits.minWidth, Math.round(width)))
}

/** The last width the user chose. Not clamped here: the grid clamps it against the current window. */
export function loadPanelWidth(limits: PanelLimits, storage: WidthStorage | undefined): number {
  try {
    const stored = Number.parseInt(storage?.getItem(limits.storageKey) ?? '', 10)
    return Number.isFinite(stored) ? stored : limits.defaultWidth
  } catch {
    return limits.defaultWidth
  }
}

export function savePanelWidth(limits: PanelLimits, storage: WidthStorage | undefined, width: number): void {
  try {
    storage?.setItem(limits.storageKey, String(width))
  } catch {
    // ponytail: blocked storage only loses the remembered width.
  }
}

/** The CSS `grid-template-columns` track for a panel flush against the right of its row. */
export const panelTrack = (limits: PanelLimits, width: number) =>
  `clamp(${limits.minWidth}px, ${width}px, ${limits.maxShare * 100}vw)`
