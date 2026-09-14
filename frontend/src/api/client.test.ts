import { describe, expect, it } from 'vitest'
import { errorDetail } from './client'

const jsonResponse = (body: unknown) => new Response(JSON.stringify(body), { status: 422 })

describe('errorDetail', () => {
  it('returns a string detail as-is', async () => {
    expect(await errorDetail(jsonResponse({ detail: 'doi_taken' }))).toBe('doi_taken')
  })

  it('reads the field names off a list of validation errors instead of showing raw JSON', async () => {
    const detail = [
      { loc: ['body', 'title'], msg: 'String should have at least 1 character', type: 'string_too_short' },
    ]
    expect(await errorDetail(jsonResponse({ detail }))).toBe('Check these fields: title.')
  })

  it('lists each invalid field once, even if more than one error names it', async () => {
    const detail = [
      { loc: ['body', 'title'], msg: 'too short', type: 'string_too_short' },
      { loc: ['body', 'year'], msg: 'not an int', type: 'int_parsing' },
      { loc: ['body', 'title'], msg: 'too long', type: 'string_too_long' },
    ]
    expect(await errorDetail(jsonResponse({ detail }))).toBe('Check these fields: title, year.')
  })

  it('falls back to a generic message when the validation errors carry no field name', () => {
    return expect(errorDetail(jsonResponse({ detail: [{ msg: 'bad' }] }))).resolves.toBe('Some details are invalid.')
  })
})
