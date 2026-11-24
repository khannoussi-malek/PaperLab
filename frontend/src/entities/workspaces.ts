import type { components } from './schema'

export type Workspace = components['schemas']['WorkspaceOut']

export type PackageRecordExists = { exists: boolean }

export type PackageImportResult = {
  workspace_id: string
  name: string
  added: number
  matched: number
  notes: number
  pdfs_skipped: number
  has_record: boolean
  answers: number
  hits: number
}
