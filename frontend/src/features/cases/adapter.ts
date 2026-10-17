import { common } from '@/i18n/cs/common'
import type { components } from '@/lib/api/schema'
import type { CaseDetail, CaseSummary, DocumentInfo } from '@/lib/domain'

type ApiCase = components['schemas']['CaseSummary']
type ApiDetail = components['schemas']['CaseDetail']
type ApiDocument = components['schemas']['DocumentSummary']

// The queue bucket is decided by the backend (contracts/case-states.md); `archiv` is filtered out by the inbox.
const COLUMN: Record<components['schemas']['QueueBucket'], CaseSummary['column']> = {
  novy: 'new',
  aktivni: 'active',
  odlozeny: 'snoozed',
  archiv: 'active',
}

export function adaptCase(c: ApiCase): CaseSummary {
  return {
    id: c.id,
    patientName: c.patient.display_name,
    birthDate: c.patient.birth_date,
    insurerCode: c.patient.insurer_code ?? null,
    state: c.state,
    column: COLUMN[c.bucket],
    baton: c.baton_holder
      ? { name: c.baton_holder.display, action: common.batonActions[c.state], due: c.next_deadline ?? null }
      : null,
    counts: {
      missing: c.counts?.missing ?? c.missing_count ?? null,
      conflict: c.counts?.conflict ?? c.conflict_count ?? null,
      stale: c.counts?.stale ?? null,
    },
    koc: c.koc ?? undefined,
    gp: c.referring_gp?.name,
    documentCount: c.document_count,
    openedAt: c.opened_at ?? null,
    gpOpenedAt: c.gp_opened_at ?? null,
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
  readinessWaivers: (c.readiness_waivers ?? []).map((w) => ({
    item: w.item,
    reason: w.reason,
    by: w.waived_by ?? null,
    at: w.waived_at,
  })),
})
