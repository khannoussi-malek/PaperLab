/** "Save as note"'s size, measured at `size="sm"`; fixed so the button can be placed before it renders. */
export const SAVE_BUTTON_WIDTH = 140
export const SAVE_BUTTON_HEIGHT = 32
const GAP = 6
const EDGE = 8

type PanelBox = { left: number; top: number; width: number; height: number }

/** Where the button floats, relative to the panel: just under the selection, and always inside the panel. */
export function saveButtonPosition(selection: { left: number; bottom: number }, panel: PanelBox) {
  const left = Math.max(EDGE, Math.min(selection.left - panel.left, panel.width - SAVE_BUTTON_WIDTH))
  const below = selection.bottom - panel.top + GAP
  const top = Math.max(EDGE, Math.min(below, panel.height - SAVE_BUTTON_HEIGHT - EDGE))
  return { left, top }
}
