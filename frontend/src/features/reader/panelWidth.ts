/** Width of the reader's right panel (Notes | Chat), in CSS px. */
export const DEFAULT_PANEL_WIDTH = 360
export const MIN_PANEL_WIDTH = 320
/** The panel can take at most this share of the window, so the paper always keeps the larger part. */
export const MAX_PANEL_SHARE = 0.6

const STORAGE_KEY = 'paperlab-panel-width'

type WidthStorage = Pick<Storage, 'getItem' | 'setItem'>

export const maxPanelWidth = (viewportWidth: number) => Math.max(MIN_PANEL_WIDTH, Math.floor(viewportWidth * MAX_PANEL_SHARE))

export function clampPanelWidth(width: number, viewportWidth: number): number {
  if (!Number.isFinite(width)) return DEFAULT_PANEL_WIDTH
  return Math.min(maxPanelWidth(viewportWidth), Math.max(MIN_PANEL_WIDTH, Math.round(width)))
}

/** The last width the user chose. Not clamped here: the grid clamps it against the current window. */
export function loadPanelWidth(storage: WidthStorage | undefined): number {
  try {
    const stored = Number.parseInt(storage?.getItem(STORAGE_KEY) ?? '', 10)
    return Number.isFinite(stored) ? stored : DEFAULT_PANEL_WIDTH
  } catch {
    return DEFAULT_PANEL_WIDTH
  }
}

export function savePanelWidth(storage: WidthStorage | undefined, width: number): void {
  try {
    storage?.setItem(STORAGE_KEY, String(width))
  } catch {
    // ponytail: blocked storage only loses the remembered width.
  }
}
