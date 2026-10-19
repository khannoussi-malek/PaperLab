import { describe, expect, it, vi } from 'vitest'
import { AlreadyInLibraryError, api, errorDetail } from './client'

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

it('AlreadyInLibraryError carries its message and the holding paper id', () => {
  const error = new AlreadyInLibraryError('This paper is already in your library.', 'p7')
  expect(error).toBeInstanceOf(Error)
  expect([error.name, error.message, error.paperId]).toEqual([
    'AlreadyInLibraryError',
    'This paper is already in your library.',
    'p7',
  ])
})

describe('api.addCandidate', () => {
  it('rejects a 409 that names a paper as AlreadyInLibraryError', async () => {
    const body = { detail: 'already_in_library', paper_id: 'p7' }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 409 })))
    const added = api.addCandidate({ title: 'T' } as never)
    await expect(added).rejects.toMatchObject({ name: 'AlreadyInLibraryError', paperId: 'p7' })
    vi.unstubAllGlobals()
  })

  it('rejects the 409 no-free-PDF answer as NoFreePdfError, whatever its sentence says', async () => {
    // The real body: the server's own sentence as `detail`, with what it tried (main.py's DomainError handler).
    const body = { detail: 'No free PDF was found for this paper. Open its page, download the PDF and use Upload PDFs.', tried: [], free_copies: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 409 })))
    await expect(api.addCandidate({ title: 'T' } as never)).rejects.toMatchObject({ name: 'NoFreePdfError', message: body.detail })
    vi.unstubAllGlobals()
  })

  it('uploads a paper PDF to /pdf as multipart field "file", and finds one at /find-pdf', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['%PDF'], 'a.pdf', { type: 'application/pdf' })
    await api.uploadPaperPdf('p1', file)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/papers/p1/pdf')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
    expect((fetchMock.mock.calls[0][1].body as FormData).get('file')).toBeInstanceOf(File)
    await api.findPaperPdf('p1')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/papers/p1/find-pdf')
    expect(fetchMock.mock.calls[1][1].method).toBe('POST')
    vi.unstubAllGlobals()
  })

  it('keeps what a failed find-pdf tried and the free copies it names', async () => {
    const body = { detail: 'no_free_pdf', tried: [{ url: 'https://a.example/x.pdf', outcome: 'http_403' }], free_copies: ['https://b.example'] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 409 })))
    await expect(api.findPaperPdf('p1')).rejects.toMatchObject({ tried: body.tried, freeCopies: body.free_copies })
    vi.unstubAllGlobals()
  })
})

describe('Zotero import forms', () => {
  const file = new File(['@article{a}'], 'refs.bib')
  const sentForm = async (call: () => Promise<unknown>) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await call()
    vi.unstubAllGlobals()
    return (fetchMock.mock.calls[0][1] as RequestInit).body as FormData
  }

  it.each([true, false])('previewImport sends save_without_pdf=%s', async (flag) => {
    const form = await sentForm(() => api.previewImport(file, flag))
    expect(form.get('save_without_pdf')).toBe(String(flag))
  })

  it.each([true, false])('startImport sends save_without_pdf=%s', async (flag) => {
    const form = await sentForm(() => api.startImport(file, {}, true, flag))
    expect(form.get('save_without_pdf')).toBe(String(flag))
  })
})
