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
