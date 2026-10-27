import { wordCount } from './sections'

export type SectionStatus = 'empty' | 'error' | 'todo' | 'ok'

const EMPTY_BELOW = 20
const TODO = /%\s*todo|\\todo\{/gi
const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

/** The dot and label for one section: error beats todo beats empty beats fine. */
export function sectionStatus(text: string, errorCount: number): { status: SectionStatus; label: string; todos: number } {
  const todos = text.match(TODO)?.length ?? 0
  if (errorCount > 0) return { status: 'error', label: plural(errorCount, 'compile error'), todos }
  if (todos > 0) return { status: 'todo', label: plural(todos, 'TODO'), todos }
  if (wordCount(text) < EMPTY_BELOW) return { status: 'empty', label: 'Empty', todos }
  return { status: 'ok', label: 'Fine', todos }
}
