import { createContext, useContext } from 'react'
import { DEFAULT_GLASS, type GlassSettings } from './settings'

export type GlassContextValue = {
  settings: GlassSettings
  update: (patch: Partial<GlassSettings>) => void
  reset: () => void
  /** False in Safari and Firefox, which can only frost. */
  bendsLight: boolean
}

export const GlassContext = createContext<GlassContextValue | null>(null)

/** Outside the provider (a component rendered on its own, as in a test) there is simply no bending. */
const NO_GLASS: GlassContextValue = { settings: DEFAULT_GLASS, update: () => {}, reset: () => {}, bendsLight: false }

/** The liquid glass settings and their setters, from LiquidGlassProvider. */
export function useGlass(): GlassContextValue {
  return useContext(GlassContext) ?? NO_GLASS
}
