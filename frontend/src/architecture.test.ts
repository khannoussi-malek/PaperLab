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

// oxlint's layer rules match `@/` paths, so a relative import that leaves its top-level folder would slip past them.
test('relative imports stay inside their own top-level folder', () => {
  const sources = import.meta.glob(['./**/*.{ts,tsx}', '!./**/*.d.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>
  const escapes: string[] = []
  for (const [file, text] of Object.entries(sources)) {
    const top = file.split('/')[1]
    for (const [, spec] of text.matchAll(/(?:from|import\(|vi\.mock\()\s*'(\.{1,2}\/[^']*)'/g)) {
      const target = new URL(spec, `file:///src/${file.slice(2)}`).pathname
      if (!target.startsWith('/src/')) continue // a package file, e.g. a test reading node_modules
      if (file.split('/').length > 2 && target.split('/')[2] !== top) escapes.push(`${file} -> ${spec}`)
    }
  }
  expect(escapes).toEqual([])
})

// Features may use each other, but every edge couples two areas. The baseline only goes down: shared pieces belong in
// components, entities, services or lib. Lower it when you remove an edge; never raise it.
const CROSS_FEATURE_EDGES = 56

test('features depend on each other no more than the baseline', () => {
  const sources = import.meta.glob(['./features/**/*.{ts,tsx}', '!./features/**/*.test.{ts,tsx}'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>
  const edges = new Set<string>()
  for (const [file, text] of Object.entries(sources)) {
    const own = file.split('/')[2]
    for (const [, spec] of text.matchAll(/(?:from|import\()\s*'([^']+)'/g)) {
      const path = spec.startsWith('@/') ? `/src/${spec.slice(2)}` : spec.startsWith('.') ? new URL(spec, `file:///src/${file.slice(2)}`).pathname : null
      const other = path?.startsWith('/src/features/') ? path.split('/')[3] : null
      if (other && other !== own) edges.add(`${own} -> ${other}`)
    }
  }
  expect(edges.size).toBeLessThanOrEqual(CROSS_FEATURE_EDGES)
})
