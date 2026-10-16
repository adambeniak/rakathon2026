// Temporary view-model types for the shell. When contracts/openapi.json lands,
// replace these with types from the generated `src/lib/api/schema.d.ts`.
import { z } from 'zod'

export const CASE_STATES = [
  'sent',
  'triage',
  'awaiting_docs',
  'complete',
  'ready_for_mdt',
  'mdt_conclusion',
  'feedback_sent',
  'closed',
] as const
export type CaseState = (typeof CASE_STATES)[number]

export const HANDOVER_STATUSES = [
  'complete',
  'partial',
  'missing',
  'stale',
  'needs_clarification',
  'complete_with_conflict',
  'generated_with_citations',
] as const
export type HandoverStatus = (typeof HANDOVER_STATUSES)[number]

export type Role = 'gp' | 'coordinator' | 'physician' | 'reviewer'

export const evidenceSchema = z.object({
  docId: z.string(),
  quote: z.string().optional(),
})
export type Evidence = z.infer<typeof evidenceSchema>

export const handoverSectionSchema = z.object({
  key: z.string(),
  number: z.number(),
  title: z.string(),
  status: z.enum(HANDOVER_STATUSES),
  rows: z.array(z.object({ label: z.string().optional(), value: z.string(), note: z.string().optional() })),
  missing: z.array(z.string()),
  evidence: z.array(evidenceSchema),
  findingIds: z.array(z.string()),
  confirmed: z.boolean(),
  confirmedBy: z.string().optional(),
})
export type HandoverSection = z.infer<typeof handoverSectionSchema>

export interface BatonHolderInfo {
  name: string
  action: string
  due: string | null // ISO date
}

export interface CaseSummary {
  id: string
  patientName: string
  birthDate: string
  diagnosis: string
  state: CaseState
  subStatus: string
  column: 'new' | 'active' | 'snoozed'
  baton: BatonHolderInfo
  counts: { missing: number; conflict: number; stale: number }
  koc: string
  gp: string
  urgent: boolean
  referredAt: string
}

export interface CaseDetail extends CaseSummary {
  birthNumber: string
  insurer: string
  t: { t1: number | null; t2: number | null; t3: number | null }
}

export interface DocumentInfo {
  id: string
  title: string
  place: string
  authored: string // ISO date
  received: string // ISO timestamp
  afterAsOf: boolean
}

export interface Finding {
  id: string
  kind: string
  severity: 'high' | 'medium' | 'low' | 'info'
  bucket: 'missing' | 'conflict' | 'stale' | 'document' | 'info'
  title: string
  detail: string
  quotes: string[]
  docIds: string[]
  visibleFrom: string // ISO date
  resolvedOn?: string
}

export interface TaskItem {
  id: string
  title: string
  owner: string
  place: string
  due: string
  doneOn?: string
  dependsOn: string[]
  state: 'open' | 'done' | 'overdue'
}

export interface TimelineEvent {
  date: string
  label: string
  note?: string
  excluded?: boolean
}

export interface Message {
  id: string
  at: string
  from: string
  to: string
  subject: string
  body: string
}

export interface AuditEntry {
  at: string
  who: string
  action: string
}
