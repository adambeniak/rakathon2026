// Insurer (ZP) analytics over a simulated cohort. Every number comes from the API; the UI never recomputes them.
import { z } from 'zod'
import { client, unwrap } from '@/lib/api/client'
import { queryKey, useApiQuery } from '@/lib/api/query'
import type { components } from '@/lib/api/schema'

type S = components['schemas']

const intervalKey = z.enum([
  'contact_to_accepted',
  'ct_order_to_ct',
  'biopsy_order_to_biopsy',
  'contact_to_mdt',
  'mdt_to_treatment',
  'contact_to_treatment',
])
const milestoneKey = z.enum([
  'gp_contacted_coordinator',
  'accepted',
  'ct_done',
  'biopsy_done',
  'mdt',
  'treatment_start',
])
const num = z.number().nullable()

const medians = z.object({
  contact_to_accepted: num,
  ct_order_to_ct: num,
  biopsy_order_to_biopsy: num,
  contact_to_mdt: num,
  mdt_to_treatment: num,
  contact_to_treatment: num,
}) satisfies z.ZodType<S['InsurerIntervalMedians']>

const hospital = z.object({
  id: z.string(),
  name: z.string(),
  simulated: z.boolean(),
  cases: z.number(),
  median_days: medians,
  median_cost_czk: num,
  median_coordinator_minutes: num,
  coordinators: z.number(),
  coordinator_minutes_total: z.number(),
  utilisation_pct: num,
  within_target_share: num,
  speed_score: num,
  cost_score: num,
  indicator: num,
  indicator_rank: num,
  badges: z.array(z.enum(['fastest', 'lowest_cost'])),
}) satisfies z.ZodType<S['HospitalAnalytics']>

const coordinator = z.object({
  id: z.string(),
  display: z.string(),
  simulated: z.boolean(),
  hospital_id: z.string(),
  hospital_name: z.string(),
  cases: z.number(),
  median_minutes_per_patient: num,
  median_days_contact_to_accepted: num,
  minutes_total: z.number(),
  utilisation_pct: num,
}) satisfies z.ZodType<S['CoordinatorAnalytics']>

const journey = z.object({
  code: z.string(),
  simulated: z.boolean(),
  hospital_id: z.string(),
  hospital_name: z.string(),
  coordinator_display: z.string(),
  milestones: z.array(
    z.object({ key: milestoneKey, date: z.string().nullable(), days_since_previous: num }),
  ),
  intervals: z.array(
    z.object({
      key: intervalKey,
      start: z.string().nullable(),
      end: z.string().nullable(),
      days: num,
      status: z.enum(['measured', 'running', 'not_started', 'not_recorded', 'inconsistent']),
    }),
  ),
  cost_czk: z.number(),
  coordinator_minutes: num,
  within_target: z.boolean().nullable(),
}) satisfies z.ZodType<S['JourneyAnalytics']>

export const insurerAnalytics = z.object({
  simulated: z.boolean(),
  disclaimer: z.string(),
  as_of: z.string(),
  assumptions: z.object({
    capacity: z.object({
      minutes_per_week: z.number(),
      period_start: z.string(),
      period_end: z.string(),
      weeks: z.number(),
      note: z.string(),
    }),
    targets: z.object({
      ct_order_to_ct_max_days: z.number(),
      biopsy_order_to_biopsy_max_days: z.number(),
      note: z.string(),
    }),
    weights: z.object({ speed: z.number(), cost: z.number(), target_share: z.number() }),
    speed_metric: intervalKey,
    formula: z.string(),
    price_list_note: z.string(),
    price_list: z.array(z.object({ code: z.string(), label: z.string(), price_czk: z.number() })),
  }),
  hospitals: z.array(hospital),
  coordinators: z.array(coordinator),
  journeys: z.array(journey),
  summary: z.object({ cases: z.number(), simulated_cases: z.number(), median_days: medians }),
  rankings: z.object({
    by_indicator: z.array(z.string()),
    fastest: z.array(z.string()),
    lowest_cost: z.array(z.string()),
  }),
}) satisfies z.ZodType<S['InsurerAnalytics']>

export type InsurerAnalytics = z.output<typeof insurerAnalytics>
export type HospitalRow = InsurerAnalytics['hospitals'][number]
export type CoordinatorRow = InsurerAnalytics['coordinators'][number]
export type JourneyRow = InsurerAnalytics['journeys'][number]
export type MilestoneKey = z.output<typeof milestoneKey>

export function useInsurerAnalytics() {
  return useApiQuery({
    key: queryKey('insurer', 'analytics'),
    schema: insurerAnalytics,
    fetch: async () => unwrap(await client.GET('/api/insurer/analytics')),
  })
}
