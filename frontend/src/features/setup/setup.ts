import type { LLMConnection } from '@/api/client'

/** The first-run setup's pure pieces (spec §5); the page is SetupPage.tsx. */

export type SetupStep = 'chat' | 'search'

export const SKIPPED = 'You can read, highlight and take notes now. Set up chat and search any time in Settings.'
export const LINUX_OLLAMA = 'Ollama must listen beyond 127.0.0.1 for PaperLab to reach it: see the README.'
/** The Search step's one line about Built-in (spec §5: "stays on this computer"); the search model download gives its size. */
export const BUILT_IN_SEARCH = 'The built-in search model stays on this computer.'

/** Opens #/setup on start while the server says setup isn't done, unless it is already open. */
export function openSetupOnStart(done: boolean, hash: string): boolean {
  return !done && hash !== '#/setup'
}

export type ChatSuggestion = { name: string; size: string; note: string }

/** The chat models setup offers to pull into Ollama (spec §5), smallest first. */
export const CHAT_SUGGESTIONS: readonly ChatSuggestion[] = [
  { name: 'qwen3:4b', size: '2.5 GB', note: 'For 8 GB of memory.' },
  { name: 'qwen3:8b', size: '5.2 GB', note: "PaperLab's default." },
]

export const pullLabel = (suggestion: ChatSuggestion) => `Pull ${suggestion.name} · ${suggestion.size}`

/** The suggestions Ollama doesn't have yet (it lists models as name:tag, as the suggestions are named). */
export const suggestedPulls = (installed: readonly string[]) =>
  CHAT_SUGGESTIONS.filter((suggestion) => !installed.includes(suggestion.name))

/** The id of a model chat already lists on this connection, or null (then it is added first). */
export const listedModelId = (connection: Pick<LLMConnection, 'models'>, name: string) =>
  connection.models.find((model) => model.name === name)?.id ?? null

/** A Linux user agent, and not Android's. */
export const isLinux = (userAgent: string) => /\bLinux\b/.test(userAgent) && !/\bAndroid\b/.test(userAgent)
