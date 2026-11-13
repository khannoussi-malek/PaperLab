import { expect, test } from 'vitest'
import { codeInWords } from './errorWords'

test('a refused write on a read-only workspace reads in plain words', () => {
  expect(codeInWords('workspace_read_only')).toBe('This workspace is read-only. Make it editable first.')
})
