import { describe, expect, it } from 'vitest'
import type { LLMConnection, SearchSource } from '@/api/client'
import {
  costWords,
  eligibleConnections,
  errorLine,
  noConnection,
  PAUSE,
  picksOf,
  rebuildLine,
  rebuildPercent,
  reindexDialog,
  samePicks,
  sourceLabel,
  sourceLine,
  switchBody,
  switchDialog,
  switchRefusal,
  tokensWords,
  whereLine,
  type SourceKind,
  type Target,
} from './searchSources'

const connection = (fields: Partial<LLMConnection>): LLMConnection => ({
  id: 'openai',
  kind: 'openai_compatible',
  label: 'OpenAI',
  base_url: 'https://api.openai.com/v1',
  has_key: true,
  key_hint: 'T123',
  is_local: false,
  models: [],
  ...fields,
})
const local = { has_key: false, key_hint: null, is_local: true }
const OPENAI = connection({})
const GEMINI = connection({ id: 'gemini', label: 'Gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai' })
const OPENROUTER = connection({ id: 'openrouter', label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1' })
const LM_STUDIO = connection({ id: 'lm-studio', label: 'LM Studio', base_url: 'http://host.docker.internal:1234/v1', ...local })
const OLLAMA = connection({ id: 'ollama', kind: 'ollama', label: 'Ollama', base_url: 'http://host.docker.internal:11434', ...local })
const EVERY = [OPENAI, GEMINI, OPENROUTER, LM_STUDIO, OLLAMA]

const library = (papers: number, notes: number, chars: number) => ({
  library_papers: papers,
  library_notes: notes,
  library_chars: chars,
})
const OWNERS = library(20, 39, 1_337_600) // spec §1: 20 papers and 39 notes
const TO_OPENAI: Target = { kind: 'openai', label: 'OpenAI', model: 'text-embedding-3-small', isLocal: false }
const OPENAI_FOOTNOTE =
  "Estimated at 4 characters a token and OpenAI's published price on 18 September 2026 ($0.02 per million tokens)."
const BUILT_IN: SearchSource = {
  kind: 'builtin',
  connection_id: null,
  connection_label: null,
  model: null,
  host: null,
  is_local: true,
  label: 'Built-in',
}
const ON_OPENAI: SearchSource = {
  kind: 'openai',
  connection_id: 'openai',
  connection_label: 'OpenAI',
  model: 'text-embedding-3-small',
  host: 'api.openai.com',
  is_local: false,
  label: 'OpenAI',
}

describe('the estimate', () => {
  it('words the tokens at their size', () => {
    expect(tokensWords(800)).toBe('about 800 tokens')
    expect(tokensWords(334_400)).toBe('about 334k tokens')
    expect(tokensWords(1_300_000)).toBe('about 1.3M tokens')
  })

  it('words the cost', () => {
    expect(costWords(0.0067)).toBe('less than $0.01')
    expect(costWords(0.026)).toBe('roughly $0.03')
    expect(costWords(12.3)).toBe('roughly $12')
  })
})

describe('switchDialog', () => {
  it('tells a cloud switch what it sends, the notes too, with its estimate and the price it assumed', () => {
    expect(switchDialog(TO_OPENAI, OWNERS)).toEqual({
      title: 'Switch search to OpenAI?',
      body: [
        'This sends the text of all 20 papers and your 39 notes (about 334k tokens, less than $0.01) to OpenAI, and each new paper, note and search question from now on.',
        PAUSE,
      ],
      footnote: [OPENAI_FOOTNOTE],
    })
    // The E2E stub's library reproduces the owner's example.
    expect(switchDialog(TO_OPENAI, library(20, 39, 5_200_000)).body[0]).toBe(
      'This sends the text of all 20 papers and your 39 notes (about 1.3M tokens, roughly $0.03) to OpenAI, and each new paper, note and search question from now on.',
    )
    expect(PAUSE).toBe('Search pauses until every paper is embedded again. Reading, notes and chat on short papers keep working.')
  })

  it('names one paper or one note, the papers alone, the notes alone, or neither', () => {
    const sends = (papers: number, notes: number, chars: number) => switchDialog(TO_OPENAI, library(papers, notes, chars)).body[0]
    const next = 'to OpenAI, and each new paper, note and search question from now on.'
    expect(sends(20, 1, 1_337_600)).toBe(`This sends the text of all 20 papers and your note (about 334k tokens, less than $0.01) ${next}`)
    expect(sends(1, 1, 3_200)).toBe(`This sends the text of your paper and your note (about 800 tokens, less than $0.01) ${next}`)
    expect(sends(20, 0, 1_337_600)).toBe(`This sends the text of all 20 papers (about 334k tokens, less than $0.01) ${next}`)
    expect(sends(0, 39, 3_200)).toBe(`This sends your 39 notes (about 800 tokens, less than $0.01) ${next}`)
    expect(sends(0, 0, 0)).toBe('This sends each new paper, note and search question to OpenAI from now on.')
  })

  it("prices OpenAI's large model and Gemini, and warns about Gemini's free tier", () => {
    const large = switchDialog({ ...TO_OPENAI, model: 'text-embedding-3-large' }, OWNERS)
    const gemini = switchDialog({ kind: 'gemini', label: 'Gemini', model: 'gemini-embedding-2', isLocal: false }, OWNERS)
    expect(large.body[0]).toContain('(about 334k tokens, roughly $0.04)')
    expect(gemini.body[0]).toContain('(about 334k tokens, roughly $0.07) to Gemini')
    expect(gemini.footnote).toEqual([
      "Estimated at 4 characters a token and Gemini's published price on 18 September 2026 ($0.20 per million tokens).",
      "On Gemini's free tier, Google may use what it receives to improve its products, and people may read it.",
    ])
  })

  it("gives a cloud server whose price PaperLab doesn't know the tokens alone, to its connection's label", () => {
    const vllm = switchDialog({ kind: 'openai_compatible', label: 'vLLM box', model: 'bge-m3', isLocal: false }, OWNERS)
    expect(vllm.body[0]).toBe(
      'This sends the text of all 20 papers and your 39 notes (about 334k tokens) to vLLM box, and each new paper, note and search question from now on.',
    )
    expect(vllm.footnote).toEqual(["Estimated at 4 characters a token. PaperLab doesn't know this server's price."])
  })

  it('tells a local switch where the passages are embedded, with no estimate', () => {
    const ollama = switchDialog({ kind: 'ollama', label: 'Ollama', model: 'nomic-embed-text', isLocal: true }, OWNERS)
    const builtIn = switchDialog({ kind: 'builtin', label: 'Built-in', model: '', isLocal: true }, OWNERS)
    expect(ollama).toEqual({
      title: 'Switch search to Ollama?',
      body: ["Every paper's passages are embedded again with nomic-embed-text on Ollama, on this computer.", PAUSE],
      footnote: [],
    })
    expect(builtIn.body[0]).toBe("Every paper's passages are embedded again with the built-in model, on this computer.")
  })
})

describe('reindexDialog', () => {
  it('says a cloud re-index sends everything again, and leaves a local one to the plain copy', () => {
    expect(reindexDialog(ON_OPENAI, OWNERS)).toEqual({
      body: [
        'This sends the text of all 20 papers and your 39 notes (about 334k tokens, less than $0.01) to OpenAI again.',
        PAUSE,
      ],
      footnote: [OPENAI_FOOTNOTE],
    })
    expect(reindexDialog(BUILT_IN, OWNERS)).toBeNull()
  })
})

describe('the rebuild', () => {
  it('counts the papers done of those there were when it started', () => {
    expect(rebuildLine('OpenAI', { done: 12, total: 20 })).toBe('Search is being rebuilt with OpenAI: 12 of 20 papers.')
    expect(rebuildLine('Ollama', { done: 1, total: 1 })).toBe('Search is being rebuilt with Ollama: 1 of 1 paper.')
    expect(rebuildLine('OpenAI', { done: 0, total: 20 })).toBe('Search is being rebuilt with OpenAI: 0 of 20 papers.')
    expect([rebuildPercent({ done: 3, total: 20 }), rebuildPercent({ done: 0, total: 0 })]).toEqual([15, 0])
  })

  it('words the last embedding failure with one period', () => {
    expect(errorLine('Key rejected by OpenAI')).toBe("Some papers couldn't be embedded: Key rejected by OpenAI.")
    expect(errorLine('Press Try again in Settings → Search.')).toBe(
      "Some papers couldn't be embedded: Press Try again in Settings → Search.",
    )
  })
})

describe('eligibleConnections', () => {
  it('offers Ollama its own kind, OpenAI and Gemini by host, and OpenAI-compatible every compatible server', () => {
    const ids = (kind: SourceKind) => eligibleConnections(kind, EVERY).map((c) => c.id)
    expect(ids('ollama')).toEqual(['ollama'])
    expect(ids('openai')).toEqual(['openai'])
    expect(ids('gemini')).toEqual(['gemini'])
    expect(ids('openai_compatible')).toEqual(['openai', 'gemini', 'openrouter', 'lm-studio'])
    expect(ids('builtin')).toEqual([])
  })
})

describe('what the picker says', () => {
  it('labels a source by its name, or by its connection for Ollama and OpenAI-compatible servers', () => {
    expect(sourceLabel('builtin')).toBe('Built-in')
    expect(sourceLabel('openai', OPENAI)).toBe('OpenAI')
    expect(sourceLabel('gemini', GEMINI)).toBe('Gemini')
    expect(sourceLabel('ollama', OLLAMA)).toBe('Ollama')
    expect(sourceLabel('openai_compatible', LM_STUDIO)).toBe('LM Studio')
    expect(sourceLine(BUILT_IN)).toBe('Search source: Built-in')
    expect(sourceLine(ON_OPENAI)).toBe('Search source: OpenAI · text-embedding-3-small')
    expect(sourceLine({ ...ON_OPENAI, kind: 'ollama', model: 'nomic-embed-text', label: 'Ollama' })).toBe(
      'Search source: Ollama · nomic-embed-text',
    )
  })

  it('says where the picked source runs', () => {
    expect(whereLine('builtin')).toBe('Runs on this computer. Nothing leaves it.')
    expect(whereLine('ollama', OLLAMA)).toBe('Runs on host.docker.internal. Nothing leaves your network.')
    expect(whereLine('openai', OPENAI)).toBe(
      'Cloud: every passage of every paper, and every search question, goes to api.openai.com.',
    )
    expect(whereLine('gemini')).toBe(
      'Cloud: every passage of every paper, and every search question, goes to generativelanguage.googleapis.com.',
    )
    expect(whereLine('ollama')).toBeNull() // no connection picked yet
  })

  it("offers a connection to add when a kind has none, and words the dialog's refusals", () => {
    expect(noConnection('openai')).toEqual({ line: 'No OpenAI connection yet.', button: 'Add OpenAI key', preset: 'OpenAI' })
    expect(noConnection('gemini')).toEqual({ line: 'No Gemini connection yet.', button: 'Add Gemini key', preset: 'Gemini' })
    expect(noConnection('ollama')).toEqual({ line: 'No Ollama connection yet.', button: 'Add Ollama', preset: 'Ollama' })
    expect(noConnection('openai_compatible')).toEqual({ line: 'No OpenAI-compatible connection yet.', button: 'Add connection' })
    expect(noConnection('builtin')).toBeNull()
    expect(switchRefusal('embedding_model_not_pulled', 'Ollama')).toBe("nomic-embed-text isn't in Ollama yet.")
    expect(switchRefusal('search_model_missing', 'Built-in')).toBe('Download the search model first.')
    expect(switchRefusal('Key rejected by OpenAI', 'OpenAI')).toBe('Key rejected by OpenAI')
  })

  it('starts from the source in use, counts as changed only when the picks differ, and sends them as the switch', () => {
    expect(picksOf(BUILT_IN)).toEqual({ kind: 'builtin', connectionId: null, model: '' })
    const same = { kind: 'openai' as const, connectionId: 'openai', model: ' text-embedding-3-small ' }
    expect(samePicks(picksOf(ON_OPENAI), same)).toBe(true)
    expect(samePicks(picksOf(ON_OPENAI), { ...same, model: 'text-embedding-3-large' })).toBe(false)
    expect(switchBody({ kind: 'builtin', connectionId: 'stale', model: 'x' })).toEqual({
      kind: 'builtin',
      connection_id: null,
      model: null,
      confirm: true,
    })
    expect(switchBody({ kind: 'openai_compatible', connectionId: 'lm-studio', model: ' bge-m3 ' })).toEqual({
      kind: 'openai_compatible',
      connection_id: 'lm-studio',
      model: 'bge-m3',
      confirm: true,
    })
  })
})
