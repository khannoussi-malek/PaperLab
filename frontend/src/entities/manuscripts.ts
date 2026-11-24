import type { components } from './schema'

export type CheckFinding = components['schemas']['CheckFindingOut']
export type CheckRunResult = components['schemas']['RunChecksOut']
export type DoiCheckResult = components['schemas']['DoiCheckOut']
export type CheckInfo = components['schemas']['CheckInfoOut']
export type Manuscript = components['schemas']['ManuscriptOut']
export type ManuscriptDetail = components['schemas']['ManuscriptDetailOut']
export type ManuscriptImport = components['schemas']['ManuscriptImportOut']
export type ManuscriptTemplate = components['schemas']['TemplateOut']
/** A reporting guideline: a named checklist the author ticks as suggestions (`GET /api/reporting-guidelines`). */
export type ReportingGuidelineItem = { id: string; section: string; text: string }
export type ReportingGuideline = { id: string; label: string; applies_to: string; source: string; items: ReportingGuidelineItem[] }
export type ManuscriptFile = components['schemas']['FileOut']
export type ManuscriptFileText = components['schemas']['FileTextOut']
export type ManuscriptSnapshot = components['schemas']['SnapshotOut']
export type EvidenceFound = components['schemas']['EvidenceFoundOut']
export type EvidenceRow = components['schemas']['EvidenceRowOut']
export type MissingKey = components['schemas']['MissingKeyOut']
export type ReviewRun = components['schemas']['ReviewRunOut']
export type CheckItem = components['schemas']['CheckItemOut']
export type ReviewState = components['schemas']['ReviewOut']
export type ReviewSentence = components['schemas']['SentenceOut']
export type ReviewStart = { file: string; base: string; from?: number | null; to?: number | null; include_uncited?: boolean; confirm_remote?: boolean }
export type ReviewEstimate = components['schemas']['EstimateOut']
export type ReviewAllStart = components['schemas']['ReviewAllIn']
export type SectionReview = components['schemas']['SectionReviewOut']
export type SectionFinding = components['schemas']['FindingOut']
export type SectionRef = components['schemas']['RefOut']
export type SectionSpan = components['schemas']['SectionSpanOut']
export type SectionReviewStart = components['schemas']['SectionReviewIn']
export type DraftReview = components['schemas']['DraftReviewOut']
export type DraftReviewEstimate = components['schemas']['DraftReviewEstimate']
export type Diagram = components['schemas']['DiagramOut']
export type DiagramStart = components['schemas']['DiagramIn']
export type CitablePaper = components['schemas']['CitablePaperOut']
export type ManuscriptCreate = components['schemas']['ManuscriptCreate']
export type ManuscriptPatch = components['schemas']['ManuscriptPatch']

export type SaveResult = { conflict: boolean; updatedAt: string }
