// MOCK: serialises the assembled sections to the wire shape of `GET /api/cases/{id}/handover` (contract `Handover`),
// so the real `adaptHandover` runs against the same shape in the mocks as against the backend.
import { handover as t } from '@/i18n/cs/handover'
import type { components } from '@/lib/api/schema'
import type { HandoverSection } from '@/lib/domain'
import type { RowEdit } from './cases'
import { DOCUMENTS, documentById, includedAt } from './documents'
import { applyEdits, sectionHash } from './handover'

type Handover = components['schemas']['Handover']

const EXCLUDED_REASON = 'Dokument vznikl nebo byl přijat po termínu as-of'
const CZ_DATE = /^(\d{1,2})\. (\d{1,2})\. (\d{4})$/

const isoDate = (note?: string): string | undefined => {
  const m = note ? CZ_DATE.exec(note) : null
  return m ? `${m[3]}-${m[2]!.padStart(2, '0')}-${m[1]!.padStart(2, '0')}` : undefined
}

const missingKey = (label: string): string => Object.entries(t.missingItems).find(([, v]) => v === label)?.[0] ?? label

function itemEvidence(row: HandoverSection['rows'][number]) {
  return (row.evidence ?? []).map((e) => {
    const d = documentById(e.docId)
    return { doc_id: e.docId, quote: e.quote ?? '', authored_at: d?.authored ?? '', received_at: d?.received ?? '' }
  })
}

/** `base`: sections as assembled (confirmations applied, no edits); `edits` are laid over them like the API does. */
export function toWire(caseId: string, asOf: string, base: HandoverSection[], edits: Record<string, Record<number, RowEdit>>): Handover {
  const reviewed = applyEdits(base, edits)
  const fields = Object.fromEntries(
    base.map((b, n) => {
      const s = reviewed[n]!
      const rowEdits = edits[s.key] ?? {}
      const edited = Object.keys(rowEdits).length > 0
      const remarks = b.rows.map((r) => r.note).filter((note): note is string => !!note && !isoDate(note))
      const field = {
        status: s.status,
        evidence: s.evidence.map((e) => ({ doc_id: e.docId, quote: e.quote ?? '' })),
        // `edit` is the provisional per-row attribution (see ItemEdit in features/handover/adapter.ts).
        items: s.rows.map((r, i) => ({
          label: r.label,
          value: r.value,
          clinical_date: isoDate(b.rows[i]?.note),
          evidence: itemEvidence(r),
          ...(rowEdits[i] ? { edit: { by: rowEdits[i].by, at: rowEdits[i].at, reason: rowEdits[i].reason } } : {}),
        })),
        missing: s.missing.map(missingKey),
        conflicts: s.findingIds,
        note: remarks.length > 0 ? remarks.join(' · ') : null,
        review: s.confirmed
          ? { state: 'confirmed', by: { display: s.confirmedBy ?? '', id: 'mock', role: 'koc_physician' }, at: new Date().toISOString(), edited }
          : edited
            ? { state: 'draft', edited }
            : null,
        value_hash: sectionHash(s),
      }
      return [s.key, field]
    }),
  )
  const included = includedAt(asOf)
  return {
    as_of: asOf,
    case_id: caseId,
    included_documents: included.map((d) => d.id),
    excluded_documents: DOCUMENTS.filter((d) => !included.includes(d)).map((d) => ({ doc_id: d.id, reason: EXCLUDED_REASON })),
    fields: fields as unknown as Handover['fields'],
  }
}

/** A case without documents: every field is missing and nothing is included. */
export function emptyWire(caseId: string, asOf: string): Handover {
  const fields = Object.fromEntries(Object.keys(t.sectionTitles).map((key) => [key, { status: 'missing', items: [], evidence: [], missing: [] }]))
  return { as_of: asOf, case_id: caseId, included_documents: [], excluded_documents: [], fields: fields as unknown as Handover['fields'] }
}
