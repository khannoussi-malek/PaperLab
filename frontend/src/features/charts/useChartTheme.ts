import { useSyncExternalStore } from 'react'
import type { ChartTheme } from './palette'

const isDark = () => document.documentElement.classList.contains('dark')

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  return () => observer.disconnect()
}

/** `'dark'` while `<html>` has the `dark` class, re-rendering on the toggle or a "System" theme following the OS. */
export function useChartTheme(): ChartTheme {
  return useSyncExternalStore(subscribe, () => (isDark() ? 'dark' : 'light'))
}
