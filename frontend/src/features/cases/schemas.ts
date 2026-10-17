// zod schemas for the case endpoints of demo steps 1–2, typed against the generated contract types.
import { z } from 'zod'
import type { components } from '@/lib/api/schema'

type Schemas = components['schemas']

const caseState = z.enum([
  'odeslano',
  'triage',
  'ceka_na_podklady',
  'kompletni',
  'pripraveno_mdt',
  'zaver_mdt',
  'zpetna_vazba_odeslana',
  'uzavreno',
])

/** The part of `CaseSummary` the step 1–2 screens read after a write: id, state and who holds the baton. */
export const caseSummary = z.object({
  id: z.string(),
  state: caseState,
  baton_holder: z.object({ id: z.string(), display: z.string(), role: z.string() }).nullish(),
})

const evidence = z.object({ doc_id: z.string(), quote: z.string() })

export const proposals = z.object({
  source_doc_id: z.string().nullish(),
  proposals: z.array(
    z.object({
      key: z.string(),
      label: z.string(),
      exam_date: z.string().nullable(),
      status: z.enum(['missing', 'attached', 'possibly_attached']),
      evidence: z.array(evidence),
      attached_doc_id: z.string().nullish(),
      recipient_name: z.string().nullish(),
      recipient_org_id: z.string().nullish(),
      resolved_by: z.string().nullish(),
    }),
  ),
}) satisfies z.ZodType<Schemas['ProposalsOut']>

const documentRequest = z.object({
  id: z.string(),
  label: z.string(),
  status: z.enum(['requested', 'accepted', 'in_progress', 'completed', 'failed', 'cancelled']),
  exam_date: z.string().nullish(),
  recipient: z.string().nullish(),
  due: z.string().nullish(),
  result_doc_id: z.string().nullish(),
})

export const documentRequests = z.array(documentRequest)

export const documentRequestsCreated = z.object({
  case: caseSummary,
  requests: z.array(documentRequest),
})

// --- Case activity: audit trail, timeline, messages (KOC team of the case) ---

const role = z.enum([
  'gp',
  'coordinator',
  'koc_physician',
  'koc_staff',
  'external_workplace',
  'patient',
  'reviewer',
  'system',
])

export const caseAuditTrail = z.object({
  case_id: z.string(),
  items: z.array(
    z.object({
      recorded: z.string(),
      actor: z.string().nullish(),
      actor_role: role.nullish(),
      on_behalf_of: z.string().nullish(),
      action: z.enum(['C', 'R', 'U', 'D', 'E']),
      operation: z.string(),
      workflow_event: z.boolean(),
      entity_types: z.array(z.string()),
      outcome: z.enum(['success', 'failure']),
    }),
  ),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  truncated: z.boolean(),
}) satisfies z.ZodType<Schemas['CaseAuditTrail']>

const timelineKind = z.enum([
  'document_authored',
  'document_received',
  'case_event',
  'request_sent',
  'request_fulfilled',
  'step_scheduled',
  'step_result_delivered',
  'step_escalated',
  'step_cancelled',
  'mdt_meeting',
  'mdt_conclusion',
  'feedback_sent',
  'feedback_delivered',
  'gp_opened',
])

export const caseTimeline = z.object({
  case_id: z.string(),
  as_of: z.string().nullish(),
  now: z.string(),
  events: z.array(
    z.object({
      id: z.string(),
      kind: timelineKind,
      at: z.string(),
      date_only: z.boolean(),
      event: z.string().nullish(),
      title: z.string().nullish(),
      place: z.string().nullish(),
      actor: z.string().nullish(),
      doc_id: z.string().nullish(),
      task_id: z.string().nullish(),
      from_state: z.string().nullish(),
      to_state: z.string().nullish(),
      receipt_id: z.string().nullish(),
      planned: z.boolean(),
      excluded_from_handover: z.boolean().nullish(),
    }),
  ),
}) satisfies z.ZodType<Schemas['CaseTimeline']>

export const caseMessages = z.array(
  z.object({
    id: z.string(),
    kind: z.enum(['document_request', 'mdt_feedback']),
    status: z.enum(['open', 'fulfilled', 'cancelled', 'sent']),
    sent_at: z.string().nullish(),
    sender: z.string().nullish(),
    recipient: z.string().nullish(),
    text: z.string(),
    request: z
      .object({
        request_id: z.string(),
        status: z.enum([
          'requested',
          'accepted',
          'in_progress',
          'completed',
          'failed',
          'cancelled',
        ]),
        due: z.string().nullish(),
        exam_date: z.string().nullish(),
        result_doc_id: z.string().nullish(),
      })
      .nullish(),
    delivery: z
      .object({
        channel: z.literal('email'),
        receipt_id: z.string().nullish(),
        gp_opened_at: z.string().nullish(),
      })
      .nullish(),
  }),
) satisfies z.ZodType<Schemas['CaseMessage'][]>

export type CaseAuditTrail = z.output<typeof caseAuditTrail>
export type AuditItem = CaseAuditTrail['items'][number]
export type CaseTimeline = z.output<typeof caseTimeline>
export type TimelineEntry = CaseTimeline['events'][number]
export type CaseMessage = z.output<typeof caseMessages>[number]
