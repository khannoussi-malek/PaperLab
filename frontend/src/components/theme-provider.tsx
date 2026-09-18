import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { withViewTransition } from '@/components/motion'

export type Theme = 'dark' | 'light' | 'system'

const STORAGE_KEY = 'paperlab-theme'

type ThemeState = { theme: Theme; setTheme: (theme: Theme) => void }

const ThemeContext = createContext<ThemeState | null>(null)

// ponytail: shadcn's Vite dark-mode provider. The class is set after first paint, so a dark
// user sees one light frame on load; add an inline script in index.html if that ever bothers.
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'system')

  useEffect(() => {
    const root = document.documentElement
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const dark = theme === 'dark' || (theme === 'system' && media.matches)
      root.classList.toggle('dark', dark)
    }
    apply()
    if (theme !== 'system') return
    media.addEventListener('change', apply)
    return () => media.removeEventListener('change', apply)
  }, [theme])

  const setTheme = (next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next)
    // A sync render flushes its effects before flushSync returns, so the class above flips inside the transition.
    withViewTransition(() => setThemeState(next))
  }

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeState {
  const context = useContext(ThemeContext)
  if (!context) throw new Error('useTheme must be used within a ThemeProvider')
  return context
}
