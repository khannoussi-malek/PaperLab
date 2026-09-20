import type { KeyboardEvent, PointerEvent } from 'react'
import { clampPanelWidth, maxPanelWidth, type PanelLimits } from './panelWidth'

const KEY_STEP_PX = 16

type Props = {
  limits: PanelLimits
  width: number
  onWidthChange: (width: number) => void
  /** The accessible name, when a view has more than one thing called a panel. */
  label?: string
  /** Pixels between the panel's right edge and the window's, when the panel isn't flush to it (a padded pane). */
  inset?: number
}

/**
 * The WAI-ARIA window splitter on a panel's left edge: drag it, use ←/→ when focused, or double-click (or Enter)
 * to go back to the default width. The panel is flush right, so its width is the window width minus the pointer's x,
 * less whatever padding sits outside it.
 */
export function PanelResizeHandle({ limits, width, onWidthChange, label = 'Resize panel', inset = 0 }: Props) {
  const resize = (next: number) => onWidthChange(clampPanelWidth(limits, next, window.innerWidth))

  function startDrag(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    event.preventDefault() // no text selection while dragging
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function drag(event: PointerEvent<HTMLDivElement>) {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) resize(window.innerWidth - inset - event.clientX)
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = { ArrowLeft: KEY_STEP_PX, ArrowRight: -KEY_STEP_PX }[event.key]
    if (step) resize(width + step)
    else if (event.key === 'Enter') onWidthChange(limits.defaultWidth)
    else return
    event.preventDefault()
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={limits.minWidth}
      aria-valuemax={maxPanelWidth(limits, window.innerWidth)}
      tabIndex={0}
      className="group absolute inset-y-0 -left-1.5 z-10 w-3 cursor-col-resize touch-none outline-none"
      onPointerDown={startDrag}
      onPointerMove={drag}
      onDoubleClick={() => onWidthChange(limits.defaultWidth)}
      onKeyDown={onKeyDown}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-primary opacity-0 transition-opacity duration-150 group-hover:opacity-60 group-focus-visible:opacity-100 group-active:opacity-100"
      />
    </div>
  )
}
