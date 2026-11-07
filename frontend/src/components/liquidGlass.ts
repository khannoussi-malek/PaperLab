/**
 * Liquid glass: where the light-bending edge of Apple's Liquid Glass can run (see "Glass" in design-system/MASTER.md).
 * The toasts' lenses themselves are in `toastLens.ts` and `Notifications.tsx`.
 */

/** The class on <html> that turns the bending on; only set where the browser can do it. */
export const LIQUID_CLASS = 'liquid'

type UserAgentData = { brands: { brand: string; version: string }[] }

/**
 * Whether this browser bends light. Only Chromium (Chrome, Edge, Arc, and the Electron desktop app) runs an SVG filter
 * inside `backdrop-filter`; Safari and Firefox drop the whole declaration, so they keep the frosted glass instead.
 */
export function bendsLight(userAgentData: UserAgentData | undefined, userAgent: string): boolean {
  if (userAgentData) return userAgentData.brands.some(({ brand }) => brand === 'Chromium')
  // Chrome, Edge and Electron all say "Chrome/"; Safari and Firefox never do.
  return /\bChrome\/\d/.test(userAgent)
}
