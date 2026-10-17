import type { components } from '@/lib/api/schema'
import type { Evidence, HandoverSection } from '@/lib/domain'

/** A document the handover leaves out (API `excluded_documents`); the API gives the reason, not the title. */
export interface ExcludedDocument {
  id: string
  reason: string
}

/** Evidence of one displayed value, with the source's dates from the API (`ItemEvidence`). */
export interface RowEvidence extends Evidence {
  authored?: string // ISO date
  received?: string // ISO timestamp
}

/** A sub-item the sources do not state, with the reason and the role that can supply it (API `missing_items`). */
export interface MissingEntry {
  key: string
  label: string
  reason: string
  /** Czech label of the suggested owner; absent when the API sent only the plain `missing` key. */
  owner?: string
}

/** Finding of the consistency detector exactly as the API words it (`Handover.findings`). */
export interface FindingView {
  id: string
  /** What the detector found (conflict, missing, stale, …) as the API classifies it; it decides the pill. */
  kind: components['schemas']['FindingKind']
  message: string
  /** Verbatim quotes the detector cites for the finding; may be empty. */
  evidence: Evidence[]
}

type Row = Omit<HandoverSection['rows'][number], 'evidence'> & { evidence?: RowEvidence[] }

/** The handover section as the screen renders it: the shared view plus what only this screen needs. */
export interface SectionView extends Omit<HandoverSection, 'rows'> {
  rows: Row[]
  missingItems: MissingEntry[]
  /** The physician accepted that the section stays missing (`review.state = accepted_missing`). */
  acceptedMissing: boolean
  /** Plain-text value of a section that can be edited inline (5, 8); absent for structured sections. */
  editableText?: string
  findings: FindingView[]
}

export interface HandoverView {
  asOf: string
  sections: SectionView[]
  excluded: ExcludedDocument[]
}
