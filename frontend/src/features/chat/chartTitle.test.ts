import { expect, test } from 'vitest'
import { chartTitle } from './chartTitle'

test('a chart answer names its chart by its bold first line, else a plain default', () => {
  expect(chartTitle('**F1 by system**\n\nOurs is higher.')).toBe('F1 by system')
  expect(chartTitle('no title here')).toBe('Chart from chat')
})
