// zod schemas for the referral endpoints, typed against the generated contract types so a contract change breaks the build.
import { z } from 'zod'
import type { Koc, ReferralPrefill } from './types'
import { caseSummary } from '@/features/cases/schemas'

const status = z.enum(['complete', 'missing', 'needs_clarification'])
const evidence = z.object({ doc_id: z.string(), quote: z.string() })

/** `Evidenced[T]` of the contract: a value (or none), its status and the verbatim quotes it was read from. */
const evidenced = <T extends z.ZodType>(value: T) =>
  z.object({
    value: value.nullish(),
    status,
    derived: z.boolean().default(false),
    note: z.string().nullish(),
    evidence: z.array(evidence).default([]),
  })

const text = evidenced(z.string())

export const kocList = z.array(
  z.object({
    id: z.string(),
    name: z.string(),
    city: z.string().nullish(),
    coordinator: z.object({ id: z.string(), display: z.string(), phone: z.string().nullish() }).nullish(),
  }),
) satisfies z.ZodType<Koc[]>

export const referralPrefill = z.object({
  doc_id: z.string(),
  authored_at: z.string().nullish(),
  given: text,
  family: text,
  sex: evidenced(z.enum(['female', 'male', 'other', 'unknown'])),
  birth_date: evidenced(z.string()),
  age_text: text,
  birth_number: text,
  birth_number_checksum_valid: z.boolean().nullish(),
  address: evidenced(
    z.object({ line: z.string(), postal_code: z.string(), city: z.string(), country: z.string().default('CZ') }),
  ),
  patient_phone: text,
  insurer_code: text,
  insurer_name: z.string().nullish(),
  contact_person: evidenced(z.object({ name: z.string(), relation: z.string(), phone: z.string().nullish() })),
  requesting_gp: text,
  requesting_gp_role_id: z.string().nullish(),
  suspected_diagnosis: evidenced(z.object({ code: z.string().nullish(), text: z.string() })),
  consent_statements: z.array(text).default([]),
  urgency_statement: text,
}) satisfies z.ZodType<ReferralPrefill>

/** `ReferralCreated`: the new case (only the fields the confirmation screen shows are read) and non-blocking warnings. */
export const referralCreated = z.object({
  case: caseSummary,
  warnings: z.array(z.string()).default([]),
})

/**
 * What the GP confirmed, sent as the JSON `payload` field. The contract types that field as a plain string, so this
 * mirrors backend `ReferralSubmission` (app/domain/referral.py) and is checked before it leaves the browser.
 */
export const referralSubmission = z.object({
  given: z.string().min(1).max(100),
  family: z.string().min(1).max(100),
  sex: z.enum(['female', 'male', 'other', 'unknown']),
  birth_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  birth_number: z.string().regex(/^\d{6}\/?\d{3,4}$/),
  insurer_code: z.string().regex(/^\d{3}$/).nullable(),
  phone: z.string().max(40).nullable(),
  address: z.object({ line: z.string(), postal_code: z.string(), city: z.string(), country: z.string() }).nullable(),
  contact_person: z.object({ name: z.string(), relation: z.string(), phone: z.string().nullable() }).nullable(),
  diagnosis_code: z.string().max(20).nullable(),
  diagnosis_text: z.string().min(1).max(300),
  koc_id: z.string().min(1).max(100),
  consent_confirmed: z.boolean(),
  priority: z.enum(['routine', 'urgent']),
  consent_statements: z.array(z.string().min(1).max(500)).max(10),
  note: z.string().max(1000).nullable(),
})
export type ReferralSubmission = z.infer<typeof referralSubmission>
