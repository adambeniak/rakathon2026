// Insurer reviewer (revizní lékař) on the contract endpoint GET /api/reviewer/cases: a minimal, pseudonymous summary
// of the reviewer's own insured persons. The backend decides what is visible; the UI renders it as received.
import { z } from 'zod'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { queryKey, useApiQuery } from '@/lib/api/query'
import type { components } from '@/lib/api/schema'

type Schemas = components['schemas']

const interval = z.object({
  days: z
    .number()
    .int()
    .nonnegative()
    .nullish()
    .transform((v) => v ?? null),
  status: z.enum(['measured', 'running', 'not_started', 'not_recorded', 'inconsistent']),
  start: z.string().nullish(),
  end: z.string().nullish(),
}) satisfies z.ZodType<Schemas['TreatmentInterval']>

export const reviewerCase = z.object({
  ref: z.string().regex(/^RV-[0-9A-F]{12}$/),
  initials: z.string(),
  birth_year: z.number().int(),
  insurer_code: z.string(),
  diagnosis_category: z.string().nullish(),
  state: z.enum([
    'odeslano',
    'triage',
    'ceka_na_podklady',
    'kompletni',
    'pripraveno_mdt',
    'zaver_mdt',
    'zpetna_vazba_odeslana',
    'uzavreno',
  ]),
  referred_on: z.string().nullish(),
  intervals: z.object({ t1: interval, t2: interval, t3: interval }),
  delivery: z.object({
    status: z.enum(['not_sent', 'handed_over', 'opened_by_gp', 'unconfirmed']),
    gp_opened_on: z.string().nullish(),
  }),
}) satisfies z.ZodType<Schemas['ReviewerCase']>

export type ReviewerCase = z.output<typeof reviewerCase>

export function useReviewerCases() {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('reviewer', 'cases', today),
    schema: z.array(reviewerCase),
    fetch: async () => unwrap(await client.GET('/api/reviewer/cases')),
  })
}
