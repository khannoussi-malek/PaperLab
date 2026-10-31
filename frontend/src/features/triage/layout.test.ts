import { expect, it } from 'vitest'
import { deskLayout } from './layout'

it('switches layout at 700 and 1100', () => {
  expect([699, 700, 1099, 1100].map(deskLayout)).toEqual(['single', 'tabs', 'tabs', 'wide'])
})
