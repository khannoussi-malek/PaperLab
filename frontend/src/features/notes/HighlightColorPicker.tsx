import { Check } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { PRESET_COLORS } from './highlightColors'

type Props = {
  value: string
  onChange: (hex: string) => void
}

const SWATCH = 'grid size-6 shrink-0 place-items-center rounded-full ring-1 ring-foreground/20'
const RAINBOW = 'conic-gradient(#f87171, #facc15, #4ade80, #60a5fa, #c084fc, #f87171)'

/** Preset swatches plus the browser's colour picker. Every swatch is named, so colour is never the only cue. */
export function HighlightColorPicker({ value, onChange }: Props) {
  const current = value.toLowerCase()
  const isCustom = !PRESET_COLORS.some((color) => color.hex === current)
  const customInput = useRef<HTMLInputElement>(null)
  const latestOnChange = useRef(onChange)

  useEffect(() => {
    latestOnChange.current = onChange
  })

  useEffect(() => {
    customInput.current!.value = current
  }, [current])

  // Commit a custom colour on the native `change` (the picker closed), not on every `input` while dragging:
  // on a saved note each commit is a PATCH.
  useEffect(() => {
    const input = customInput.current!
    const commit = () => latestOnChange.current(input.value)
    input.addEventListener('change', commit)
    return () => input.removeEventListener('change', commit)
  }, [])

  return (
    <div role="group" aria-label="Highlight colour" className="flex items-center gap-1.5">
      {PRESET_COLORS.map((color) => (
        <button
          key={color.hex}
          type="button"
          aria-label={color.name}
          aria-pressed={color.hex === current}
          title={color.name}
          className={cn(SWATCH, 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring')}
          style={{ backgroundColor: color.hex }}
          onClick={() => onChange(color.hex)}
        >
          {color.hex === current && <Check aria-hidden className="size-3.5 text-slate-900" />}
        </button>
      ))}
      <label
        title="Custom colour"
        className={cn(
          SWATCH,
          'relative cursor-pointer has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring',
        )}
        style={{ background: isCustom ? current : RAINBOW }}
      >
        {isCustom && <Check aria-hidden className="size-3.5 text-white mix-blend-difference" />}
        <input
          ref={customInput}
          type="color"
          aria-label="Custom colour"
          className="absolute inset-0 size-full cursor-pointer opacity-0"
        />
      </label>
    </div>
  )
}
