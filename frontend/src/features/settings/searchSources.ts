import type { EmbeddingStatus, LLMConnection, Rebuild, SearchSource, SearchSourceIn } from '@/api/client'
import { hostOf } from './connectionForm'

/** A search source's kind (D131), as the API types it: the picker's list is checked against it. */
export type SourceKind = SearchSource['kind']
/** What the switch dialog's estimate reads (D157). P3 = A: the notes go too, and `library_chars` counts them. */
export type Library = Pick<EmbeddingStatus, 'library_papers' | 'library_notes' | 'library_chars'>
/** What the owner picked: the kind, the connection it runs on (none for Built-in) and its model. */
export type SourcePick = { kind: SourceKind; connectionId: string | null; model: string }
/** Where a switch goes, as the dialog words it. */
export type Target = { kind: SourceKind; label: string; model: string; isLocal: boolean }
export type Dialog = { title: string; body: string[]; footnote: string[] }

export const SOURCE_KINDS: SourceKind[] = ['builtin', 'ollama', 'openai', 'gemini', 'openai_compatible']
export const SOURCE_NAMES: Record<SourceKind, string> = {
  builtin: 'Built-in',
  ollama: 'Ollama',
  openai: 'OpenAI',
  gemini: 'Gemini',
  openai_compatible: 'OpenAI-compatible',
}
// The backend refuses any other OpenAI model (embedding_sources.OPENAI_MODELS; Correction 9): ada-002 can't give 768.
export const OPENAI_MODELS = ['text-embedding-3-small', 'text-embedding-3-large'] as const
export const GEMINI_MODEL = 'gemini-embedding-2'
export const OLLAMA_MODEL = 'nomic-embed-text'
const FIXED_HOSTS: Partial<Record<SourceKind, string>> = {
  openai: 'api.openai.com',
  gemini: 'generativelanguage.googleapis.com',
}

/** Paid-tier prices per million tokens as published on PRICES_CHECKED (D157). The switch dialog is the only reader. */
export const PRICES: Record<string, number> = {
  'text-embedding-3-small': 0.02,
  'text-embedding-3-large': 0.13,
  [GEMINI_MODEL]: 0.2,
}
export const PRICES_CHECKED = '2026-09-18'
/** OpenAI's rule of thumb for English. No tokenizer: the dialog says "about". */
export const CHARS_PER_TOKEN = 4

export const PAUSE = 'Search pauses until every paper is embedded again. Reading, notes and chat on short papers keep working.'
export const READY_AGAIN = 'Search is ready again.'
export const NOT_PULLED = 'embedding_model_not_pulled'
export const PULL_LABEL = `Pull ${OLLAMA_MODEL} · 274 MB`
const GEMINI_FREE_TIER = "On Gemini's free tier, Google may use what it receives to improve its products, and people may read it."

/** The connections a kind can run on (D151): Ollama its own kind; OpenAI and Gemini by host; any compatible server. */
export function eligibleConnections(kind: SourceKind, connections: LLMConnection[]): LLMConnection[] {
  return connections.filter((connection) => {
    if (kind === 'ollama') return connection.kind === 'ollama'
    if (kind === 'builtin' || connection.kind !== 'openai_compatible') return false
    const host = FIXED_HOSTS[kind]
    return host === undefined || hostOf(connection.kind, connection.base_url) === host
  })
}

/** The model a kind starts on: fixed for Ollama and Gemini, text-embedding-3-small for OpenAI, typed by hand otherwise. */
export function defaultModel(kind: SourceKind): string {
  if (kind === 'ollama') return OLLAMA_MODEL
  if (kind === 'openai') return OPENAI_MODELS[0]
  if (kind === 'gemini') return GEMINI_MODEL
  return ''
}

/** In messages and copy: Built-in, OpenAI and Gemini by name, Ollama and compatible servers by their connection's label. */
export function sourceLabel(kind: SourceKind, connection?: LLMConnection): string {
  if (kind === 'ollama' || kind === 'openai_compatible') return connection?.label ?? SOURCE_NAMES[kind]
  return SOURCE_NAMES[kind]
}

/** Settings → Search's first line: "Search source: OpenAI · text-embedding-3-small"; Built-in has no model. */
export function sourceLine(source: SearchSource): string {
  return source.model ? `Search source: ${source.label} · ${source.model}` : `Search source: ${source.label}`
}

/** The muted line under the picker: where the picked source runs. Null until a connection-based kind has one. */
export function whereLine(kind: SourceKind, connection?: LLMConnection): string | null {
  if (kind === 'builtin') return 'Runs on this computer. Nothing leaves it.'
  const host = connection ? hostOf(connection.kind, connection.base_url) : FIXED_HOSTS[kind]
  if (host === undefined) return null
  if (connection?.is_local) return `Runs on ${host}. Nothing leaves your network.`
  return `Cloud: every passage of every paper, and every search question, goes to ${host}.`
}

/** What the picker offers when a kind has no connection yet; `preset` starts M9's connection dialog on it. */
export function noConnection(kind: SourceKind): { line: string; button: string; preset?: string } | null {
  if (kind === 'builtin') return null
  if (kind === 'openai_compatible') return { line: 'No OpenAI-compatible connection yet.', button: 'Add connection' }
  const name = SOURCE_NAMES[kind]
  return { line: `No ${name} connection yet.`, button: kind === 'ollama' ? 'Add Ollama' : `Add ${name} key`, preset: name }
}

export function tokensWords(tokens: number): string {
  if (tokens < 1_000) return `about ${tokens} tokens`
  if (tokens < 1_000_000) return `about ${Math.round(tokens / 1_000)}k tokens`
  return `about ${(tokens / 1_000_000).toFixed(1)}M tokens`
}

export function costWords(dollars: number): string {
  if (dollars < 0.01) return 'less than $0.01'
  if (dollars < 10) return `roughly $${dollars.toFixed(2)}`
  return `roughly $${Math.round(dollars)}`
}

/** OpenAI's and Gemini's published prices; a compatible server's or a remote Ollama's is unknown. */
function priceOf(target: Target): number | undefined {
  return target.kind === 'openai' || target.kind === 'gemini' ? PRICES[target.model] : undefined
}

/** "the text of all 20 papers and your 39 notes (about 334k tokens, less than $0.01)", or null when there is nothing. */
function whatIsSent(library: Library, price: number | undefined): string | null {
  const papers = library.library_papers
  const notes = library.library_notes
  const parts = [
    papers === 0 ? null : papers === 1 ? 'the text of your paper' : `the text of all ${papers} papers`,
    notes === 0 ? null : notes === 1 ? 'your note' : `your ${notes} notes`,
  ].filter((part) => part !== null)
  if (parts.length === 0) return null
  const tokens = Math.round(library.library_chars / CHARS_PER_TOKEN)
  const cost = price === undefined ? '' : `, ${costWords((tokens * price) / 1_000_000)}`
  return `${parts.join(' and ')} (${tokensWords(tokens)}${cost})`
}

function checkedOn(): string {
  const date = new Date(PRICES_CHECKED)
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
}

function footnotes(target: Target): string[] {
  const price = priceOf(target)
  const estimate =
    price === undefined
      ? "Estimated at 4 characters a token. PaperLab doesn't know this server's price."
      : `Estimated at 4 characters a token and ${target.label}'s published price on ${checkedOn()} ($${price.toFixed(2)} per million tokens).`
  return target.kind === 'gemini' ? [estimate, GEMINI_FREE_TIER] : [estimate]
}

/** "Switch search to <label>?" (P2, D157): a cloud target says what it sends and roughly what it costs; a local one
 * says where the passages are embedded. Every switch pauses search until it is done (P1). */
export function switchDialog(target: Target, library: Library): Dialog {
  const title = `Switch search to ${target.label}?`
  if (target.isLocal) {
    const how = target.kind === 'builtin' ? 'with the built-in model' : `with ${target.model} on ${target.label}`
    return { title, body: [`Every paper's passages are embedded again ${how}, on this computer.`, PAUSE], footnote: [] }
  }
  const sent = whatIsSent(library, priceOf(target))
  const first =
    sent === null
      ? `This sends each new paper, note and search question to ${target.label} from now on.`
      : `This sends ${sent} to ${target.label}, and each new paper, note and search question from now on.`
  return { title, body: [first, PAUSE], footnote: footnotes(target) }
}

/** M9's Re-index dialog while a cloud source is active: it sends everything again. Null for a local source, whose
 * dialog keeps M9's copy. */
export function reindexDialog(source: SearchSource, library: Library): Omit<Dialog, 'title'> | null {
  if (source.is_local) return null
  const target: Target = { kind: source.kind, label: source.label, model: source.model ?? '', isLocal: false }
  const sent = whatIsSent(library, priceOf(target))
  const body = sent === null ? [PAUSE] : [`This sends ${sent} to ${source.label} again.`, PAUSE]
  return { body, footnote: footnotes(target) }
}

/** A refusal of the switch, in the dialog: the codes the dialog words itself; any other sentence as the API sent it. */
export function switchRefusal(detail: string, label: string): string {
  if (detail === NOT_PULLED) return `${OLLAMA_MODEL} isn't in ${label} yet.`
  if (detail === 'search_model_missing') return 'Download the search model first.'
  return detail
}

/** P1's line: "Search is being rebuilt with OpenAI: 12 of 20 papers." */
export function rebuildLine(label: string, rebuild: Rebuild): string {
  const papers = rebuild.total === 1 ? 'paper' : 'papers'
  return `Search is being rebuilt with ${label}: ${rebuild.done} of ${rebuild.total} ${papers}.`
}

export function rebuildPercent(rebuild: Rebuild): number {
  return rebuild.total === 0 ? 0 : Math.floor((rebuild.done / rebuild.total) * 100)
}

/** The last embedding failure (D155), with one period whatever the reason ends with. */
export function errorLine(error: string): string {
  return `Some papers couldn't be embedded: ${error.replace(/\.$/, '')}.`
}

/** The picker's starting picks: the source in use. */
export function picksOf(source: SearchSource): SourcePick {
  return { kind: source.kind, connectionId: source.connection_id ?? null, model: source.model ?? '' }
}

export function samePicks(a: SourcePick, b: SourcePick): boolean {
  return a.kind === b.kind && a.connectionId === b.connectionId && a.model.trim() === b.model.trim()
}

/** PUT /api/embedding/source's body. Built-in takes no connection or model. */
export function switchBody(picks: SourcePick): SearchSourceIn {
  const builtIn = picks.kind === 'builtin'
  return {
    kind: picks.kind,
    connection_id: builtIn ? null : picks.connectionId,
    model: builtIn ? null : picks.model.trim(),
    confirm: true,
  }
}
