import type { ChatAnswer } from '@/api/client'

type Threaded = Pick<ChatAnswer, 'id' | 'parent_id'>

/** A saved answer in panel order. `reply`: a follow-up, indented under the first question of its thread. */
export type Placed<T> = { answer: T; reply: boolean }

/**
 * Saved answers (oldest first, as the API lists them) in panel order: each thread's first question, then every
 * follow-up in that thread, oldest first, one indent level however deep the replies go. A follow-up whose answer isn't
 * listed starts its own thread.
 *
 * `liveParentId`: the answer a streaming follow-up was asked with. Its live copy goes at `liveAt`, the end of that
 * thread; a question asked on its own (or whose thread is gone) goes last.
 */
export function threadOrder<T extends Threaded>(answers: T[], liveParentId: string | null = null) {
  const byId = new Map(answers.map((answer) => [answer.id, answer]))
  const rootOf = (answer: T): T => {
    const parent = answer.parent_id === null ? undefined : byId.get(answer.parent_id)
    return parent ? rootOf(parent) : answer
  }
  // A root is older than its follow-ups, so each thread's key is inserted by its first question, in history order.
  const threads = new Map<string, T[]>()
  for (const answer of answers) {
    const root = rootOf(answer).id
    threads.set(root, [...(threads.get(root) ?? []), answer])
  }
  const liveParent = liveParentId === null ? undefined : byId.get(liveParentId)
  const liveRoot = liveParent ? rootOf(liveParent).id : null
  const placed: Placed<T>[] = []
  let liveAt = -1
  for (const [root, thread] of threads) {
    placed.push(...thread.map((answer) => ({ answer, reply: answer.id !== root })))
    if (root === liveRoot) liveAt = placed.length
  }
  return { placed, liveAt: liveRoot === null ? placed.length : liveAt, liveReply: liveRoot !== null }
}
