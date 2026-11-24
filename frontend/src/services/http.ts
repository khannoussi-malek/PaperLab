/** The last `loc` segment of each FastAPI validation error that has one, deduplicated and in order. */
function invalidFields(errors: unknown[]): string[] {
  const fields = errors.flatMap((error) => {
    const loc = typeof error === 'object' && error !== null && 'loc' in error ? (error as { loc: unknown }).loc : null
    const field = Array.isArray(loc) ? loc.at(-1) : null
    return typeof field === 'string' ? [field] : []
  })
  return [...new Set(fields)]
}

/** A failed response's `detail` as readable text. FastAPI sends a string, or a list of validation errors. */
export async function errorDetail(response: Response): Promise<string> {
  const detail: unknown = await response.json().then((body) => body?.detail ?? response.statusText, () => response.statusText)
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const fields = invalidFields(detail)
    return fields.length > 0 ? `Check these fields: ${fields.join(', ')}.` : 'Some details are invalid.'
  }
  return JSON.stringify(detail)
}

/** A 409 that names the library paper already holding what was being added (or imported). */
export class AlreadyInLibraryError extends Error {
  readonly paperId: string

  constructor(message: string, paperId: string) {
    super(message)
    this.name = 'AlreadyInLibraryError'
    this.paperId = paperId
  }
}

/** The 410 a merged paper's id gets: it names the paper it was merged into. */
export class PaperMergedError extends Error {
  readonly keptId: string

  constructor(message: string, keptId: string) {
    super(message)
    this.name = 'PaperMergedError'
    this.keptId = keptId
  }
}

/** The 409 an Add gets when no free PDF was found: it carries what was tried, and the paper can be saved without one. */
export class NoFreePdfError extends Error {
  readonly tried: { url: string; outcome: string }[]
  readonly freeCopies: string[]

  constructor(message: string, tried: { url: string; outcome: string }[] = [], freeCopies: string[] = []) {
    super(message)
    this.name = 'NoFreePdfError'
    this.tried = tried
    this.freeCopies = freeCopies
  }
}

/** Any other failed response: `code` is the server's `detail` and `body` the rest of its JSON (path, limit, updated_at…). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly body: Record<string, unknown>

  constructor(message: string, status: number, body: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = typeof body.detail === 'string' ? body.detail : message
    this.body = body
  }
}

/** True for a 409 ApiError whose server code is `code` (changed_since, already_undone, not_a_desk_event). */
export const isConflict = (e: unknown, code: string) => e instanceof ApiError && e.status === 409 && e.code === code

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const parsed: unknown = await response.clone().json().catch(() => null)
    const body: Record<string, unknown> = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {}
    const message = await errorDetail(response)
    // The typed errors keep the statuses they always had; any other failure is an ApiError.
    if (response.status === 409 || response.status === 410) {
      if (response.status === 410 && typeof body.kept_id === 'string') throw new PaperMergedError(message, body.kept_id)
      if (typeof body.paper_id === 'string') throw new AlreadyInLibraryError(message, body.paper_id)
      // no_free_pdf's detail is the server's sentence; its `tried` list is what marks it (main.py's DomainError handler)
      if (Array.isArray(body.tried))
        throw new NoFreePdfError(message, body.tried as NoFreePdfError['tried'], Array.isArray(body.free_copies) ? (body.free_copies as string[]) : [])
    }
    throw new ApiError(message, response.status, body)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const sendJson = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})
