import { expect, test } from 'vitest'
import { tagErrorText } from './tagErrors'

test('known codes read in plain words, anything else stays as it is', () => {
  expect(tagErrorText('tag_exists')).toBe('A tag with that name already exists.')
  expect(tagErrorText('invalid_tag_name')).toBe('Tag names are 1 to 64 characters.')
  expect(tagErrorText('boom')).toBe('boom')
})
