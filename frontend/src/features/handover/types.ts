import type { HandoverSection } from '@/lib/domain'

/** A document the handover leaves out (API `excluded_documents`); the API gives the reason, not the title. */
export interface ExcludedDocument {
  id: string
  reason: string
}

export interface HandoverView {
  asOf: string
  sections: HandoverSection[]
  excluded: ExcludedDocument[]
}
