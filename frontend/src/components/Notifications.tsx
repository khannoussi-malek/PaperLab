import { Toaster } from 'sileo'
import { useTheme } from '@/components/theme-provider'

// Below the shell's h-11 toolbar, so a toast never covers the view's title or actions.
const TOOLBAR_HEIGHT = 44

/**
 * PaperLab's passing notices: Sileo's toasts, in Sileo's own colours (see "Notifications" in design-system/MASTER.md).
 * Sileo is told the app's theme so it picks its own matching fill and text; without it, dark mode drew the app's light
 * text on Sileo's default white pill. Mount once at the app root, inside ThemeProvider, then call
 * `sileo.success({ title })` and friends from anywhere.
 */
export function Notifications() {
  const { theme } = useTheme()
  return <Toaster position="top-right" offset={{ top: TOOLBAR_HEIGHT }} theme={theme} options={{ duration: 4000 }} />
}
