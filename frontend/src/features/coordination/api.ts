import { useMemo } from 'react'
import { z } from 'zod'
import { client, unwrap } from '@/lib/api/client'
import { queryKey, useApiMutation, useApiQuery } from '@/lib/api/query'
import { pragueLocalToIso } from '@/lib/date'

// --- Board lanes are the backend `Role` enum; the lane type lives here, not in lib/domain.
export const ROLES = [
  'gp',
  'coordinator',
  'koc_physician',
  'koc_staff',
  'external_workplace',
  'patient',
  'reviewer',
  'system',
] as const
export type BoardRole = (typeof ROLES)[number]
const role = z.enum(ROLES)

export const BUSINESS_STATUSES = ['objednano', 'potvrzeno', 'provedeno', 'vysledek_dorucen'] as const
export type BusinessStatus = (typeof BUSINESS_STATUSES)[number]

const owner = z.object({ id: z.string(), display: z.string(), role })

const task = z.object({
  id: z.string(),
  code: z.string(),
  title: z.string(),
  status: z.enum(['requested', 'accepted', 'in_progress', 'completed', 'failed', 'cancelled']),
  business_status: z.enum(BUSINESS_STATUSES).nullish(),
  lane: role,
  owner: owner.nullish(),
  recorded_on_behalf_by: owner.nullish(),
  place: z.string().nullish(),
  due: z.string().nullish(),
  sla_due: z.string().nullish(),
  scheduled_at: z.string().nullish(),
  escalated_at: z.string().nullish(),
  overdue: z.boolean(),
  overdue_workdays: z.number(),
  depends_on: z.array(z.string()),
  blocked_by: z.array(z.string()),
  result_doc_id: z.string().nullish(),
})
export type BoardTask = z.infer<typeof task>

const batonHolder = z.object({
  role,
  owner: owner.nullish(),
  task_id: z.string(),
  task_title: z.string(),
  reason: z.enum(['action', 'awaiting_confirmation', 'dependency_failed']),
  due: z.string().nullish(),
})
export type BoardBaton = z.infer<typeof batonHolder>

const board = z.object({
  computed_at: z.string(),
  baton_holder: batonHolder.nullish(),
  lanes: z.array(z.object({ role, tasks: z.array(task) })),
})
export type Board = z.infer<typeof board>

const pathwayLaunched = z.object({ plan_url: z.string(), start_date: z.string(), tasks: z.array(task) })

const caseDocuments = z.object({ documents: z.array(z.object({ doc_id: z.string(), title: z.string() })) })

export const PANCREAS_PLAN_URL = 'https://stafeta.example/fhir/PlanDefinition/pancreas-dx'

/** Demo MDT start (21. 10. 2026 8:00, Prague); the launch form shows it and lets the coordinator change it. */
export const DEMO_MDT_START_LOCAL = '2026-10-21T08:00'

/**
 * Seeded KOC 2 physicians who can indicate the set (PractitionerRole business ids).
 * The directory (`GET /api/directory/kocs`) lists no physicians, so the demo offers the seeded ones, MDT chair first.
 * TODO(#67) read them from the directory once it exposes them.
 */
export const KOC_PHYSICIANS: ReadonlyArray<{ id: string; display: string }> = [
  { id: 'hruby-pavel@koc2-nemocnice-lipova', display: 'doc. MUDr. Pavel Hrubý, Ph.D. (předseda MDT GIT)' },
  { id: 'svoboda-martin@koc2-nemocnice-lipova', display: 'MUDr. Martin Svoboda (gastroenterolog, endoskopista)' },
  { id: 'markova-lenka@koc2-nemocnice-lipova', display: 'MUDr. Lenka Marková (klinická onkologie)' },
]

export function useBoard(caseId: string) {
  return useApiQuery({
    key: queryKey('coordination', caseId, 'board'),
    schema: board,
    fetch: async () => unwrap(await client.GET('/api/cases/{case_id}/board', { params: { path: { case_id: caseId } } })),
  })
}

/** Open-step summary for the case overview ("Nejbližší kroky"); done/overdue come from the API flags. */
export interface TaskSummary {
  id: string
  title: string
  owner: string
  due: string
  state: 'open' | 'done' | 'overdue'
}

/** The board's tasks as the overview lists them, earliest due first. Steps without a planned date are left out. */
export function useTasks(caseId: string) {
  const q = useBoard(caseId)
  const data = useMemo<TaskSummary[] | undefined>(
    () =>
      q.data?.lanes
        .flatMap((l) => l.tasks)
        .flatMap((x) =>
          x.due
            ? [
                {
                  id: x.id,
                  title: x.title,
                  owner: x.owner?.display ?? '—',
                  due: x.due,
                  state: x.status === 'completed' ? ('done' as const) : x.overdue ? ('overdue' as const) : ('open' as const),
                },
              ]
            : [],
        )
        .sort((a, b) => a.due.localeCompare(b.due)),
    [q.data],
  )
  return { ...q, data }
}

export interface LaunchInput {
  startDate: string
  indicatedBy: string
  /** Prague wall-clock `YYYY-MM-DDTHH:mm` as the datetime-local input gives it. */
  mdtStartLocal: string
}

/** Request body of `POST /api/cases/{id}/pathways`. */
export const launchBody = (v: LaunchInput) => ({
  plan_url: PANCREAS_PLAN_URL,
  start_date: v.startDate,
  indicated_by: v.indicatedBy,
  mdt_start: pragueLocalToIso(v.mdtStartLocal),
})

export function useLaunchPathway(caseId: string) {
  return useApiMutation({
    schema: pathwayLaunched,
    mutate: async (v: LaunchInput) =>
      unwrap(await client.POST('/api/cases/{case_id}/pathways', { params: { path: { case_id: caseId } }, body: launchBody(v) })),
  })
}

export type TransitionInput =
  | { taskId: string; event: 'confirm'; place: string; date: string }
  | { taskId: string; event: 'perform' }
  | { taskId: string; event: 'deliver_result'; documentId: string }

/** Request body of `POST /api/tasks/{id}/transitions`. */
export function transitionBody(v: TransitionInput) {
  if (v.event === 'confirm') return { event: v.event, place: v.place, date: v.date }
  if (v.event === 'deliver_result') return { event: v.event, document_id: v.documentId }
  return { event: v.event }
}

export function useTransitionTask() {
  return useApiMutation({
    schema: task,
    mutate: async (v: TransitionInput) =>
      unwrap(await client.POST('/api/tasks/{task_id}/transitions', { params: { path: { task_id: v.taskId } }, body: transitionBody(v) })),
  })
}

/** Documents of the case for the "result delivered" form. */
export function useResultDocuments(caseId: string, enabled: boolean) {
  return useApiQuery({
    key: queryKey('coordination', caseId, 'documents'),
    schema: caseDocuments,
    enabled,
    fetch: async () => unwrap(await client.GET('/api/cases/{case_id}', { params: { path: { case_id: caseId } } })),
  })
}
