/** One server-sent event: its name (`message` when the server sent none) and its data lines joined by "\n". */
export type SseRecord = { event: string; data: string }

/**
 * Returns a push parser for a `text/event-stream` body read in arbitrary chunks. Each call takes the next chunk
 * and returns the events it completed; an event split across chunks, even mid-character, waits for its blank line.
 * `EventSource` can't be used: it only does GET, and chat is a POST (spec U5).
 */
export function sseParser(): (chunk: Uint8Array) => SseRecord[] {
  const decoder = new TextDecoder()
  let buffer = ''

  return (chunk) => {
    buffer = (buffer + decoder.decode(chunk, { stream: true })).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? '' // the last block is incomplete until a blank line ends it
    return blocks.flatMap((block) => {
      let event = 'message'
      const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith(':')) continue // a comment, e.g. FastAPI's keep-alive ": ping"
        const colon = line.indexOf(':')
        const field = colon === -1 ? line : line.slice(0, colon)
        const value = colon === -1 ? '' : line.slice(colon + 1).replace(/^ /, '')
        if (field === 'event') event = value
        if (field === 'data') data.push(value)
      }
      return data.length > 0 ? [{ event, data: data.join('\n') }] : []
    })
  }
}

/** Every event in a response body, in order, as it arrives. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseRecord> {
  const parse = sseParser()
  const reader = body.getReader()
  for (;;) {
    const { done, value } = await reader.read()
    if (done) return
    yield* parse(value)
  }
}
