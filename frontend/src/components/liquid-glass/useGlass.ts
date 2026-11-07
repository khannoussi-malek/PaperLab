import { createContext, useContext } from 'react'
import type { GlassSettings } from './settings'

export type GlassContextValue = {
  settings: GlassSettings
  update: (patch: Partial<GlassSettings>) => void
  reset: () => void
  /** False in Safari and Firefox, which can only frost. */
  bendsLight: boolean
}

export const GlassContext = createContext<GlassContextValue | null>(null)

/** The liquid glass settings and their setters; inside LiquidGlassProvider only. */
export function useGlass(): GlassContextValue {
  const context = useContext(GlassContext)
  if (!context) throw new Error('useGlass must be used inside LiquidGlassProvider')
  return context
}
