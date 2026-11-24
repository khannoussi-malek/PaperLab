import { chatApi } from './chat'
import { citationsApi } from './citations'
import { datasetsApi } from './datasets'
import { discoveryApi } from './discovery'
import { evidenceApi } from './evidence'
import { graphApi } from './graph'
import { llmApi } from './llm'
import { manuscriptsApi } from './manuscripts'
import { notesApi } from './notes'
import { papersApi } from './papers'
import { referencesApi } from './references'
import { searchApi } from './search'
import { settingsApi } from './settings'
import { tagsApi } from './tags'
import { triageApi } from './triage'
import { workspacesApi } from './workspaces'

/** Every endpoint in one object. Callers and tests (vi.spyOn(api, …)) share it, so a spy reaches every caller. */
export const api = {
  ...chatApi,
  ...citationsApi,
  ...datasetsApi,
  ...discoveryApi,
  ...evidenceApi,
  ...graphApi,
  ...llmApi,
  ...manuscriptsApi,
  ...notesApi,
  ...papersApi,
  ...referencesApi,
  ...searchApi,
  ...settingsApi,
  ...tagsApi,
  ...triageApi,
  ...workspacesApi,
}

export { AlreadyInLibraryError, ApiError, errorDetail, isConflict, NoFreePdfError, PaperMergedError } from '../http'
export { ALREADY_SAVED } from './chat'
export { citationsUrl, zoteroZipUrl } from './citations'
export { notesZipUrl, packageRecordUrl, packageUrl } from './workspaces'
