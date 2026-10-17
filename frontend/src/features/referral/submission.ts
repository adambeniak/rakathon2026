import { referralSubmission, type ReferralSubmission } from './schemas'
import type { Priority, ReferralPrefill } from './types'

/** Required by the backend `ReferralSubmission`; a value the letter does not state is never filled in. */
export const REQUIRED = ['family', 'given', 'birth_date', 'birth_number', 'suspected_diagnosis'] as const
export type RequiredField = (typeof REQUIRED)[number]

const has = (v: string | null | undefined): v is string => typeof v === 'string' && v.trim() !== ''

export function missingFields(p: ReferralPrefill): RequiredField[] {
  const value = (f: RequiredField) => (f === 'suspected_diagnosis' ? p.suspected_diagnosis.value?.text : p[f].value)
  return REQUIRED.filter((f) => !has(value(f)))
}

/** Preselected only when the letter itself asks for urgency (it has a quote); the GP confirms or changes it. */
export function defaultPriority(p: ReferralPrefill): Priority {
  return has(p.urgency_statement.value) && (p.urgency_statement.evidence?.length ?? 0) > 0 ? 'urgent' : 'routine'
}

export function buildSubmission(
  p: ReferralPrefill,
  input: { kocId: string; consent: boolean; priority: Priority; note: string },
): ReferralSubmission | null {
  const diagnosis = p.suspected_diagnosis.value
  const insurer = p.insurer_code.value
  const contact = p.contact_person.value
  const parsed = referralSubmission.safeParse({
    given: p.given.value,
    family: p.family.value,
    sex: p.sex.value ?? 'unknown',
    birth_date: p.birth_date.value,
    birth_number: p.birth_number.value,
    insurer_code: has(insurer) ? insurer : null,
    phone: has(p.patient_phone.value) ? p.patient_phone.value : null,
    address: p.address.value ? { ...p.address.value, country: p.address.value.country ?? 'CZ' } : null,
    contact_person: contact ? { ...contact, phone: contact.phone ?? null } : null,
    diagnosis_code: diagnosis?.code ?? null,
    diagnosis_text: diagnosis?.text,
    koc_id: input.kocId,
    consent_confirmed: input.consent,
    priority: input.priority,
    consent_statements: (p.consent_statements ?? []).map((s) => s.value).filter(has),
    note: input.note.trim() || null,
  })
  return parsed.success ? parsed.data : null
}
