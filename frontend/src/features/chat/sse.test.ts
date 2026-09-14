import { describe, expect, it } from 'vitest'
import { readSse, sseParser } from './sse'

const bytes = (text: string) => new TextEncoder().encode(text)

describe('sseParser', () => {
  it('reads several events from one chunk', () => {
    const parse = sseParser()
    expect(parse(bytes('event: sources\ndata: {"a":1}\n\nevent: token\ndata: {"text":"Hi"}\n\n'))).toEqual([
      { event: 'sources', data: '{"a":1}' },
      { event: 'token', data: '{"text":"Hi"}' },
    ])
  })

  it('waits for the blank line when an event is split across chunks, even inside a character', () => {
    const parse = sseParser()
    const wire = bytes('event: token\ndata: {"text":"✦ AI"}\n\n')
    const cut = wire.indexOf(0xe2) + 1 // the middle of the three-byte "✦"
    expect(parse(wire.slice(0, cut))).toEqual([])
    expect(parse(wire.slice(cut, -1))).toEqual([])
    expect(parse(wire.slice(-1))).toEqual([{ event: 'token', data: '{"text":"✦ AI"}' }])
  })

  it('joins multi-line data with newlines', () => {
    const parse = sseParser()
    expect(parse(bytes('event: token\ndata: first\ndata: second\n\n'))).toEqual([
      { event: 'token', data: 'first\nsecond' },
    ])
  })

  it('skips comments and keep-alive pings, accepts CRLF, and defaults the event name', () => {
    const parse = sseParser()
    expect(parse(bytes(': ping\r\n\r\ndata:no-space\r\n\r\n'))).toEqual([{ event: 'message', data: 'no-space' }])
  })
})

describe('readSse', () => {
  it('yields every event of a streamed body, however it is chunked', async () => {
    const wire = bytes('event: sources\ndata: {}\n\nevent: token\ndata: {"text":"a"}\n\nevent: done\ndata: {}\n\n')
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (let i = 0; i < wire.length; i += 7) controller.enqueue(wire.slice(i, i + 7))
        controller.close()
      },
    })
    const events: string[] = []
    for await (const record of readSse(body)) events.push(record.event)
    expect(events).toEqual(['sources', 'token', 'done'])
  })
})
