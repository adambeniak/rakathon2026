// MOCK: serialises the assembled sections to the wire shape of `GET /api/cases/{id}/handover` (contract `Handover`),
// so the real `adaptHandover` runs against the same shape in the mocks as against the backend.
import { handover as t } from '@/i18n/cs/handover'
import type { components } from '@/lib/api/schema'
import type { HandoverSection } from '@/lib/domain'
import type { RowEdit } from './cases'
import { DOCUMENTS, documentById, includedAt } from './documents'
import { FINDINGS } from './findings'
import { applyEdits, sectionHash } from './handover'

type Handover = components['schemas']['Handover']
type Role = components['schemas']['Role']
type FindingKind = components['schemas']['FindingKind']

/** Label the API gives an item whose value is the physician's own (`EDITED_LABEL` in backend/app/extraction/handover/review.py). */
export const EDITED_LABEL = 'Upraveno lékařem'
/** Plain-text sections: the API gives their `value` as a string, so the physician can edit them (`edited_value`). */
const TEXT_SECTIONS = new Set(['5_mdt_question', '8_allergies'])
const NOT_STATED = 'v dokumentaci neuvedeno'
/** Who the API names as the supplier of a missing item (backend `_missing(item, owner)`). */
const OWNER: Record<string, Role> = { ecog: 'koc_physician', patient_email: 'coordinator', tnm_clinical_stage: 'koc_physician' }

// Sections the physician accepted as missing; keyed on the `confirmed` map so `resetStore()` clears them with it.
const accepted = new WeakMap<object, Set<string>>()
export function acceptedMissing(confirmed: Record<string, string>): Set<string> {
  let set = accepted.get(confirmed)
  if (!set) accepted.set(confirmed, (set = new Set()))
  return set
}

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
export function toWire(
  caseId: string,
  asOf: string,
  base: HandoverSection[],
  edits: Record<string, Record<number, RowEdit>>,
  acceptedKeys: ReadonlySet<string> = new Set(),
): Handover {
  const reviewed = applyEdits(base, edits)
  const fields = Object.fromEntries(
    base.map((b, n) => {
      const s = reviewed[n]!
      const rowEdits = edits[s.key] ?? {}
      const edited = Object.keys(rowEdits).length > 0
      // An edited section shows the physician's value without document evidence and is no longer missing.
      const filled = edited && s.status === 'missing'
      const missingKeys = filled ? [] : s.key === '9_performance_status' && s.status === 'missing' ? ['ecog'] : s.missing.map(missingKey)
      const remarks = b.rows.map((r) => r.note).filter((note): note is string => !!note && !isoDate(note))
      const field = {
        status: filled ? 'complete' : s.status,
        value: TEXT_SECTIONS.has(s.key) && s.status !== 'missing' ? (s.rows[0]?.value ?? null) : null,
        evidence: s.evidence.map((e) => ({ doc_id: e.docId, quote: e.quote ?? '' })),
        items: edited
          ? s.rows.map((r) => ({ label: EDITED_LABEL, value: r.value, evidence: [] }))
          : s.rows.map((r, i) => ({ label: r.label, value: r.value, clinical_date: isoDate(b.rows[i]?.note), evidence: itemEvidence(r) })),
        missing: missingKeys,
        missing_items: missingKeys.map((item) => ({ item, reason: NOT_STATED, suggested_owner: OWNER[item] ?? 'coordinator' })),
        conflicts: s.findingIds,
        note: remarks.length > 0 ? remarks.join(' · ') : null,
        review: s.confirmed
          ? { state: acceptedKeys.has(s.key) ? 'accepted_missing' : 'confirmed', by: { display: s.confirmedBy ?? '', id: 'mock', role: 'koc_physician' }, at: new Date().toISOString(), edited }
          : edited
            ? { state: 'draft', edited }
            : null,
        value_hash: sectionHash(s),
      }
      return [s.key, field]
    }),
  )
  const included = includedAt(asOf)
  const referenced = new Set(base.flatMap((s) => s.findingIds))
  return {
    findings: FINDINGS.filter((f) => referenced.has(f.id)).map((f) => ({
      id: f.id,
      kind: f.kind as FindingKind,
      severity: f.severity,
      message: f.detail,
      // Quotes are paired with a document only when the finding names exactly one (the golden file does not pair them otherwise).
      evidence: f.docIds.length === 1 ? f.quotes.map((quote) => ({ doc_id: f.docIds[0]!, quote })) : [],
    })),
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
