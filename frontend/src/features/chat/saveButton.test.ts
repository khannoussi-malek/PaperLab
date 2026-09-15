import { describe, expect, it } from 'vitest'
import { SAVE_BUTTON_HEIGHT, SAVE_BUTTON_WIDTH, saveButtonPosition } from './saveButton'

const PANEL = { left: 1000, top: 100, width: 360, height: 700 }

describe('saveButtonPosition', () => {
  it('sits just under the selection, from its left edge', () => {
    expect(saveButtonPosition({ left: 1050, bottom: 300 }, PANEL)).toEqual({ left: 50, top: 206 })
  })

  it('keeps the button inside the panel horizontally', () => {
    expect(saveButtonPosition({ left: 990, bottom: 300 }, PANEL).left).toBe(8)
    expect(saveButtonPosition({ left: 1350, bottom: 300 }, PANEL).left).toBe(360 - SAVE_BUTTON_WIDTH)
  })

  it('keeps the button inside the panel when the selection ends at, or past, its bottom or above its top', () => {
    expect(saveButtonPosition({ left: 1050, bottom: 795 }, PANEL).top).toBe(700 - SAVE_BUTTON_HEIGHT - 8)
    expect(saveButtonPosition({ left: 1050, bottom: 2000 }, PANEL).top).toBe(700 - SAVE_BUTTON_HEIGHT - 8)
    expect(saveButtonPosition({ left: 1050, bottom: 20 }, PANEL).top).toBe(8)
  })
})
