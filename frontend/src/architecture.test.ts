import { expect, test } from 'vitest'
import routerView from './router/RouterView.tsx?raw'

// Layer imports are checked by oxlint (.oxlintrc.json); this file checks what a lint rule can't see.

test('every route loads its page from src/pages, and every page there is routed', () => {
  const imported = [...routerView.matchAll(/import\('([^']+)'\)/g)].map((m) => m[1])
  expect(imported.length).toBeGreaterThan(0)
  for (const spec of imported) expect(spec).toMatch(/^@\/pages\/[A-Za-z]+Page$/)

  const pages = Object.keys(import.meta.glob('./pages/*Page.tsx')).map((path) => path.replace('./', '@/').replace('.tsx', ''))
  expect(new Set(imported)).toEqual(new Set(pages))
})
