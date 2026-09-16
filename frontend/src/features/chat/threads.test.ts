import { describe, expect, it } from 'vitest'
import { threadOrder } from './threads'

const answer = (id: string, parent_id: string | null = null) => ({ id, parent_id })

/** The panel order as ids, a follow-up indented by two spaces, plus where a live answer would go. */
function order(answers: ReturnType<typeof answer>[], liveParentId: string | null = null) {
  const { placed, liveAt, liveReply } = threadOrder(answers, liveParentId)
  return { ids: placed.map(({ answer, reply }) => (reply ? `  ${answer.id}` : answer.id)), liveAt, liveReply }
}

describe('threadOrder', () => {
  it('keeps questions asked on their own oldest first, with a new question going last', () => {
    expect(order([answer('1'), answer('2')])).toEqual({ ids: ['1', '2'], liveAt: 2, liveReply: false })
  })

  it('puts every follow-up under the first question of its thread, one level deep, oldest first', () => {
    // 3 follows 1; 4 follows 3, a follow-up to a follow-up; 5 follows 2.
    const answers = [answer('1'), answer('2'), answer('3', '1'), answer('4', '3'), answer('5', '2')]
    expect(order(answers).ids).toEqual(['1', '  3', '  4', '2', '  5'])
  })

  it('starts a thread at a follow-up whose answer is no longer listed', () => {
    expect(order([answer('1'), answer('2', 'gone'), answer('3', '2')]).ids).toEqual(['1', '2', '  3'])
  })

  it('places a streaming follow-up at the end of its thread', () => {
    const answers = [answer('1'), answer('2'), answer('3', '1')]
    expect(order(answers, '3')).toMatchObject({ liveAt: 2, liveReply: true })
    expect(order(answers, '1')).toMatchObject({ liveAt: 2, liveReply: true })
    expect(order(answers, '2')).toMatchObject({ liveAt: 3, liveReply: true })
    expect(order(answers, 'gone')).toMatchObject({ liveAt: 3, liveReply: false })
  })
})
