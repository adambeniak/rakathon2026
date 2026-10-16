// Temporary view-model types for the shell. When contracts/openapi.json lands,
// replace these with types from the generated `src/lib/api/schema.d.ts`.
import { z } from 'zod'

// Codes are the backend's (contracts/case-states.md); labels live in i18n/cs/common.ts.
export const CASE_STATES = [
  'odeslano',
  'triage',
  'ceka_na_podklady',
  'kompletni',
  'pripraveno_mdt',
  'zaver_mdt',
  'zpetna_vazba_odeslana',
  'uzavreno',
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
  rows: z.array(
    z.object({
      label: z.string().optional(),
      value: z.string(),
      note: z.string().optional(),
      /** Consent / personal wishes: shown with their source, never editable. */
      readOnly: z.boolean().optional(),
      evidence: z.array(evidenceSchema).optional(),
    }),
  ),
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

/** Counts the consistency detector has not computed yet are `null` (rendered as "—", never as 0). */
export interface FindingCounts {
  missing: number | null
  conflict: number | null
  stale: number | null
}

/**
 * View-model of a case. Only the first block comes from `GET /api/cases`; the optional fields are not in the
 * contract yet and render as "—" when absent (never filled with defaults).
 */
export interface CaseSummary {
  id: string
  patientName: string
  birthDate: string
  insurerCode: string | null
  state: CaseState
  column: 'new' | 'active' | 'snoozed'
  baton: BatonHolderInfo | null
  counts: FindingCounts
  documentCount: number
  openedAt: string | null
  // --- not in the contract (mock / portal endpoints only) ---
  insurer?: string
  diagnosis?: string
  subStatus?: string
  koc?: string
  gp?: string
  urgent?: boolean
  referredAt?: string
}

export interface CaseDetail extends CaseSummary {
  birthNumber?: string
  t?: { t1: number | null; t2: number | null; t3: number | null }
}

export interface DocumentInfo {
  id: string
  title: string
  place: string
  authored: string // ISO date
  received: string // ISO timestamp
  /** Set by the API (handover `excluded_documents`); the UI never derives it from dates. */
  afterAsOf?: boolean
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

// Lanes of the "Kdo je na tahu" board; the phase is the lifecycle a task goes through.
export const TASK_LANES = ['gp', 'coordinator', 'koc_physician', 'external', 'patient'] as const
export type TaskLane = (typeof TASK_LANES)[number]
export const TASK_PHASES = ['to_order', 'ordered', 'performed', 'result_delivered'] as const
export type TaskPhase = (typeof TASK_PHASES)[number]

export interface TaskItem {
  id: string
  title: string
  owner: string
  place: string
  due: string
  doneOn?: string
  dependsOn: string[]
  state: 'open' | 'done' | 'overdue'
  lane: TaskLane
  phase: TaskPhase
}

/** A document request proposed by the triage step (one per missing report). */
export interface DocumentRequest {
  id: string
  title: string
  recipient: string
  docId: string
  requested: boolean
  evidence: Evidence
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
