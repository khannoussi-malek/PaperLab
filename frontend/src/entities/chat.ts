import type { components } from './schema'

/** How an AI answer or note was made (M33), read on request. */
export type AnswerProvenance = components['schemas']['AnswerProvenanceOut']
export type AnswerCheck = components['schemas']['AnswerCheckOut']
export type AnswerCheckSentence = components['schemas']['AnswerCheckSentenceOut']
export type AnswerPassage = components['schemas']['AnswerPassageOut']
export type ChatSource = components['schemas']['ChatSource']
export type ChatAnswer = components['schemas']['ChatAnswer']
// Prefixed: the DOM already has a global `ErrorEvent`.
export type HitMetaEvent = components['schemas']['HitMetaEvent']
export type ChatSourcesEvent = components['schemas']['SourcesEvent']
export type ChatTokenEvent = components['schemas']['TokenEvent']
export type ChatDoneEvent = components['schemas']['DoneEvent']
export type ReadingEvent = components['schemas']['ReadingEvent']
export type ReadingOut = components['schemas']['ReadingOut']
export type ReadingPassage = components['schemas']['ReadingPassage']
export type ChatErrorEvent = components['schemas']['ErrorEvent']

/** Where a chat lives: the reader's paper, a workspace, or a search hit (abstract-only until it has full text). */
export type ChatScope = { kind: 'paper' | 'workspace'; id: string } | { kind: 'hit'; workspaceId: string; id: string; paperId?: string }
