import { handover as t } from '@/i18n/cs/handover'
import type { components } from '@/lib/api/schema'
import { formatDate } from '@/lib/date'
import type { FindingView, HandoverView, MissingEntry, SectionView } from './types'

type Handover = components['schemas']['Handover']
type Item = components['schemas']['HandoverItem']
/** Every one of the 15 fields shares this base; only `value` differs and the UI renders `items` instead. */
type Field = Omit<components['schemas']['TextField'], 'value'>
type SectionKey = keyof typeof t.sectionTitles

// The schema lists the fields alphabetically; the handover reads in the order of the MDT form.
export const SECTION_KEYS = Object.keys(t.sectionTitles) as SectionKey[]

/** Sections whose `value` is a plain string: the only ones the physician can edit inline (`edited_value` is a string). */
const EDITABLE_TEXT: ReadonlySet<string> = new Set(['5_mdt_question', '8_allergies'])

function valueOf(i: Item): string {
  const v = typeof i.value === 'number' ? String(i.value).replace('.', ',') : i.value
  return i.unit ? `${v} ${i.unit}` : v
}

function adaptItem(key: SectionKey, i: Item): SectionView['rows'][number] {
  const evidence = (i.evidence ?? []).map((e) => ({ docId: e.doc_id, quote: e.quote || undefined, authored: e.authored_at, received: e.received_at }))
  const value = valueOf(i)
  return {
    label: i.label ?? undefined,
    value,
    note: i.clinical_date ? formatDate(i.clinical_date) : undefined,
    evidence: evidence.length > 0 ? evidence : undefined,
    // Consent and wishes of the patient are shown with their own source and cannot be edited.
    readOnly: key === '15_other' && /^Souhlas/.test(value) && evidence.length > 0 ? true : undefined,
  }
}

function adaptMissing(f: Field): MissingEntry[] {
  const labelOf = (key: string): string => (t.missingItems as Record<string, string>)[key] ?? key
  const detailed = f.missing_items ?? []
  const known = new Set(detailed.map((m) => m.item))
  return [
    ...detailed.map((m) => ({ key: m.item, label: labelOf(m.item), reason: m.reason, owner: t.ownerRoles[m.suggested_owner] })),
    // A key without detail still shows; no owner is invented for it.
    ...(f.missing ?? []).filter((k) => !known.has(k)).map((k) => ({ key: k, label: labelOf(k), reason: t.missingNoReason })),
  ]
}

function adaptField(key: SectionKey, f: Field, findings: ReadonlyMap<string, FindingView>): SectionView {
  const review = f.review
  const state = review?.state
  const text = (f as { value?: unknown }).value
  const missingItems = adaptMissing(f)
  return {
    key,
    number: Number(key.split('_')[0]),
    title: t.sectionTitles[key],
    status: f.status,
    rows: (f.items ?? []).map((i) => adaptItem(key, i)),
    missing: missingItems.map((m) => m.label),
    missingItems,
    evidence: (f.evidence ?? []).map((e) => ({ docId: e.doc_id, quote: e.quote || undefined })),
    findingIds: f.conflicts ?? [],
    findings: (f.conflicts ?? []).flatMap((id) => findings.get(id) ?? []),
    // Accepting a missing section counts as reviewed: the Composition is final at 15 of 15.
    confirmed: state === 'confirmed' || state === 'accepted_missing',
    acceptedMissing: state === 'accepted_missing',
    confirmedBy: state === 'confirmed' || state === 'accepted_missing' ? review?.by?.display : undefined,
    note: f.note ?? undefined,
    edited: review?.edited || undefined,
    valueHash: f.value_hash ?? undefined,
    editableText: EDITABLE_TEXT.has(key) && (typeof text === 'string' || text == null) ? (text ?? '') : undefined,
  }
}

/** Wire shape (`as_of`, `fields`, `excluded_documents[].doc_id`) → the view the handover screen renders. */
export function adaptHandover(h: Handover): HandoverView {
  const findings = new Map((h.findings ?? []).map((f) => [f.id, { id: f.id, kind: f.kind, message: f.message, evidence: (f.evidence ?? []).map((e) => ({ docId: e.doc_id, quote: e.quote })) }]))
  return {
    asOf: h.as_of,
    // Without a single usable document nothing was assembled: the screen shows its empty state, not 15 blank sections.
    sections: h.included_documents.length === 0 ? [] : SECTION_KEYS.map((key) => adaptField(key, h.fields[key] as Field, findings)),
    excluded: (h.excluded_documents ?? []).map((d) => ({ id: d.doc_id, reason: d.reason || t.excludedReasonUnknown })),
  }
}
