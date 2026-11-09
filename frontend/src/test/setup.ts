// Adds jest-dom matchers (toBeInTheDocument, etc.) to vitest's expect, for component tests.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// RTL's own auto-cleanup only registers when `afterEach` is a global (Jest-style); this project
// doesn't enable vitest's `globals`, so unmount each rendered component by hand between tests.
afterEach(() => cleanup())

// jsdom lacks these; the chat panel uses them when it mounts inside other screens' tests.
if (typeof window !== 'undefined') {
  globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
  Element.prototype.scrollTo ??= () => {}
  Element.prototype.scrollIntoView ??= () => {}
}
