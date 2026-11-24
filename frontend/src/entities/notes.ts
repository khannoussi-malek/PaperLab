import type { components } from './schema'

export type NoteCounts = Record<string, components['schemas']['PaperNoteCounts']>
export type Note = components['schemas']['NoteOut']
export type NoteKind = NonNullable<Note['kind']>
export type McpNoteProvenance = components['schemas']['McpNoteOut']
export type FigureNoteCreate = components['schemas']['FigureNoteCreate']
export type NoteCreate = components['schemas']['NoteCreate']
export type NoteUpdate = components['schemas']['NoteUpdate']
export type NoteSource = components['schemas']['NoteSource']
export type SavedNote = components['schemas']['SavedNoteOut']
export type PromoteRequest = components['schemas']['PromoteRequest']
export type NoteSuggestion = components['schemas']['NoteSuggestionOut']
export type NoteSuggestionsOut = components['schemas']['NoteSuggestionsOut']
export type Check = components['schemas']['CheckOut']

export type NotesImportResult = {
  created: number
  linked_papers: number
  unmatched_files: number
  skipped_duplicates: number
}
