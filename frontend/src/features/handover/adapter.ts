import { handover as t } from '@/i18n/cs/handover'
import type { components } from '@/lib/api/schema'
import { formatDate } from '@/lib/date'
import type { HandoverSection } from '@/lib/domain'
import type { HandoverView } from './types'

type Handover = components['schemas']['Handover']
type Item = components['schemas']['HandoverItem']
/** Every one of the 15 fields shares this base; only `value` differs and the UI renders `items` instead. */
type Field = Omit<components['schemas']['TextField'], 'value'>
type SectionKey = keyof typeof t.sectionTitles

/** Clinician correction attributed to one row. Not in the contract (`/edit` is provisional): the API records only `review.edited`. */
export interface ItemEdit {
  by: string
  at: string
  reason: string
}
type ItemWithEdit = Item & { edit?: ItemEdit }

// The schema lists the fields alphabetically; the handover reads in the order of the MDT form.
export const SECTION_KEYS = Object.keys(t.sectionTitles) as SectionKey[]

function valueOf(i: Item): string {
  const v = typeof i.value === 'number' ? String(i.value).replace('.', ',') : i.value
  return i.unit ? `${v} ${i.unit}` : v
}

function adaptItem(key: SectionKey, i: ItemWithEdit): HandoverSection['rows'][number] {
  const evidence = (i.evidence ?? []).map((e) => ({ docId: e.doc_id, quote: e.quote || undefined }))
  const value = valueOf(i)
  return {
    label: i.label ?? undefined,
    value,
    note: i.edit ? t.editedNote(i.edit.by, i.edit.at, i.edit.reason) : i.clinical_date ? formatDate(i.clinical_date) : undefined,
    evidence: evidence.length > 0 ? evidence : undefined,
    // Consent and wishes of the patient are shown with their own source and cannot be edited.
    readOnly: key === '15_other' && /^Souhlas/.test(value) && evidence.length > 0 ? true : undefined,
  }
}

function adaptField(key: SectionKey, f: Field): HandoverSection {
  const review = f.review
  return {
    key,
    number: Number(key.split('_')[0]),
    title: t.sectionTitles[key],
    status: f.status,
    rows: (f.items ?? []).map((i) => adaptItem(key, i)),
    missing: (f.missing ?? []).map((m) => (t.missingItems as Record<string, string>)[m] ?? m),
    evidence: (f.evidence ?? []).map((e) => ({ docId: e.doc_id, quote: e.quote || undefined })),
    findingIds: f.conflicts ?? [],
    confirmed: review?.state === 'confirmed',
    confirmedBy: review?.state === 'confirmed' ? review.by?.display : undefined,
    note: f.note ?? undefined,
    edited: review?.edited || undefined,
    valueHash: f.value_hash ?? undefined,
  }
}

/** Wire shape (`as_of`, `fields`, `excluded_documents[].doc_id`) → the view the handover screen renders. */
export function adaptHandover(h: Handover): HandoverView {
  return {
    asOf: h.as_of,
    // Without a single usable document nothing was assembled: the screen shows its empty state, not 15 blank sections.
    sections: h.included_documents.length === 0 ? [] : SECTION_KEYS.map((key) => adaptField(key, h.fields[key] as Field)),
    excluded: (h.excluded_documents ?? []).map((d) => ({ id: d.doc_id, reason: d.reason || t.excludedReasonUnknown })),
  }
}
