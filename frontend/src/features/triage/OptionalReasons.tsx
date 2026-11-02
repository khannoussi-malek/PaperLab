import { useEffect, useState } from 'react'
import { LATE_CHIP_KEYS, PILES, REASONS, type Pile } from './piles'
import { ReasonChips } from './ReasonChips'

const SHOWN_MS = 4000

type Props = { pile: Pile; tall: boolean; onPick: (reason: string) => void; onExpire: () => void }

/** The chips after Read closely, Skim or Later: never waited for, gone after 4 s unless a pointer or focus is on them. */
export function OptionalReasons({ pile, tall, onPick, onExpire }: Props) {
  const [held, setHeld] = useState(false)
  useEffect(() => {
    if (held) return
    const t = setTimeout(onExpire, SHOWN_MS)
    return () => clearTimeout(t)
  }, [held, onExpire])
  const label = `Why ${PILES[pile].label}? Optional`
  return (
    <div
      className="flex flex-wrap items-center gap-2 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-150"
      onPointerEnter={() => setHeld(true)}
      onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <span aria-hidden className="text-sm text-muted-foreground">{label}</span>
      <ReasonChips label={label} firstKey={Number(LATE_CHIP_KEYS[0])} tall={tall} reasons={REASONS[pile]} onPick={(r) => onPick(r)} />
    </div>
  )
}
