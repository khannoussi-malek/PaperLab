import { useEffect, useState } from 'react'
import { delayedIn } from '@/components/motion'
import { cn } from '@/lib/utils'

const SLOW_MS = 3000

/** The extra line a slow or retrying load shows: nothing for 3 s, then "Still loading…"; "trying again" once a request has failed. */
export function useLoadingHint(failureCount = 0): string | null {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_MS)
    return () => clearTimeout(timer)
  }, [])
  if (failureCount > 0) return "The app didn't answer; trying again…"
  return slow ? 'Still loading…' : null
}

/** A bare loading line that says so when the load is slow or retrying. */
export function LoadingState({ label = 'Loading…', failureCount, className }: { label?: string; failureCount?: number; className?: string }) {
  const hint = useLoadingHint(failureCount)
  return (
    <div role="status" aria-live="polite" className={cn('text-muted-foreground', delayedIn, className)}>
      <p>{label}</p>
      {hint && <p className="text-xs">{hint}</p>}
    </div>
  )
}
