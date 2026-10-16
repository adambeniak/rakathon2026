import { common } from '@/i18n/cs/common'
import type { components } from '@/lib/api/schema'
import type { CaseDetail, CaseState, CaseSummary, DocumentInfo } from '@/lib/domain'

type ApiCase = components['schemas']['CaseSummary']
type ApiDetail = components['schemas']['CaseDetail']
type ApiDocument = components['schemas']['DocumentSummary']

// Only `odeslano` waits in "Nový". The contract has no postponed flag yet, so "Odložený" stays empty.
const columnOf = (state: CaseState): CaseSummary['column'] => (state === 'odeslano' ? 'new' : 'active')

export function adaptCase(c: ApiCase): CaseSummary {
  return {
    id: c.id,
    patientName: c.patient.display_name,
    birthDate: c.patient.birth_date,
    insurerCode: c.patient.insurer_code ?? null,
    state: c.state,
    column: columnOf(c.state),
    baton: c.baton_holder
      ? { name: c.baton_holder.display, action: common.batonActions[c.state], due: c.next_deadline ?? null }
      : null,
    counts: { missing: c.missing_count ?? null, conflict: c.conflict_count ?? null, stale: null },
    documentCount: c.document_count,
    openedAt: c.opened_at ?? null,
  }
}

export function adaptDocument(d: ApiDocument): DocumentInfo {
  return {
    id: d.doc_id,
    title: d.title,
    place: d.custodian ?? '—',
    authored: d.authored_at,
    received: d.received_at,
  }
}

export const adaptDetail = (c: ApiDetail): CaseDetail & { documents: DocumentInfo[] } => ({
  ...adaptCase(c),
  documents: c.documents.map(adaptDocument),
})
