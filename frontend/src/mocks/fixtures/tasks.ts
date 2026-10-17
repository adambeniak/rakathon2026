// MOCK copy – replaced by API in F2/F3
import type { components } from '@/lib/api/schema'
import type { TaskItem, TaskPhase } from '@/lib/domain'
import { DEMO_USERS } from './people'

type Board = components['schemas']['Board']
type TaskOut = components['schemas']['TaskOut']
type Role = components['schemas']['Role']

const BASE: Array<Omit<TaskItem, 'state' | 'phase'>> = [
  { id: 't-req', title: 'Vyžádat výsledky 01–06', owner: DEMO_USERS.coordinator.name, place: 'KOC 2 – koordinace', due: '2026-10-06', doneOn: '2026-10-08', dependsOn: [], lane: 'coordinator' },
  { id: 't-ct', title: 'CT hrudníku a břicha (pankreatický protokol)', owner: 'KOC 1 – radiologie', place: 'KOC 1 – Nemocnice Severní', due: '2026-10-08', doneOn: '2026-10-08', dependsOn: [], lane: 'external' },
  { id: 't-eus', title: 'EUS-FNB', owner: 'KOC 2 – endoskopie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-12', doneOn: '2026-10-12', dependsOn: ['t-ct'], lane: 'koc_physician' },
  { id: 't-lab', title: 'Odběry vč. nádorových markerů', owner: 'KOC 2 – laboratoř', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-15', doneOn: '2026-10-15', dependsOn: [], lane: 'external' },
  { id: 't-hist', title: 'Histologie', owner: 'KOC 2 – patologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-15', doneOn: '2026-10-19', dependsOn: ['t-eus'], lane: 'external' },
  { id: 't-verify', title: 'Ověřit rozpor v datech (apixaban, datum odběru)', owner: DEMO_USERS.coordinator.name, place: 'KOC 2 – koordinace', due: '2026-10-21', dependsOn: ['t-hist'], lane: 'coordinator' },
  { id: 't-algo', title: 'Algeziologické vyšetření', owner: 'KOC 2 – algeziologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-26', doneOn: '2026-10-26', dependsOn: [], lane: 'koc_physician' },
  { id: 't-psy', title: 'Psychologické vyšetření', owner: 'KOC 2 – psychologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-27', doneOn: '2026-10-27', dependsOn: [], lane: 'koc_physician' },
]

/**
 * Tasks of the started set. Before the coordinator starts it (demo step 4 on 2. 10.) there are none; afterwards a
 * task is done by date (history) or by the phase the user advanced it to.
 */
export function tasksAt(today: string, setStarted = false, phases: Record<string, TaskPhase> = {}): TaskItem[] {
  if (today <= '2026-10-02' && !setStarted) return []
  return BASE.map((t) => {
    const byDate = t.doneOn !== undefined && t.doneOn <= today
    const phase: TaskPhase = byDate ? 'result_delivered' : (phases[t.id] ?? 'to_order')
    const done = phase === 'result_delivered'
    const state: TaskItem['state'] = done ? 'done' : t.due < today ? 'overdue' : 'open'
    return { ...t, state, phase, doneOn: byDate ? t.doneOn : undefined }
  })
}

/** Earliest due date among tasks not done yet, honouring the phases the user has already advanced. */
export function nextDeadline(today: string, phases: Record<string, TaskPhase> = {}): { title: string; due: string; owner: string } | null {
  const open = tasksAt(today, true, phases)
    .filter((t) => t.state !== 'done')
    .sort((a, b) => a.due.localeCompare(b.due))[0]
  return open ? { title: open.title, due: open.due, owner: open.owner } : null
}

// --- Contract shape (`GET /api/cases/{id}/board`) built from the same tasks. Mock-only logic: the real backend
// computes overdue, escalation and the baton; the UI never does.

const LANE_ROLE: Record<TaskItem['lane'], Role> = {
  gp: 'gp',
  coordinator: 'coordinator',
  koc_physician: 'koc_physician',
  external: 'external_workplace',
  patient: 'patient',
}
const BOARD_ROLES: Role[] = ['gp', 'coordinator', 'koc_physician', 'external_workplace', 'patient']
const COORDINATOR = { id: 'dvorakova-lucie@koc2-nemocnice-lipova', display: DEMO_USERS.coordinator.name, role: 'coordinator' } as const
const BUSINESS: Record<TaskPhase, NonNullable<TaskOut['business_status']>> = {
  to_order: 'objednano',
  ordered: 'potvrzeno',
  performed: 'provedeno',
  result_delivered: 'vysledek_dorucen',
}
const STATUS: Record<TaskPhase, TaskOut['status']> = {
  to_order: 'requested',
  ordered: 'accepted',
  performed: 'in_progress',
  result_delivered: 'completed',
}
// The histology is promised for 15. 10. (SLA) but planned for 19. 10.; the board counts from the earlier date.
const WIRE_DATES: Record<string, { due: string; sla?: string }> = { 't-hist': { due: '2026-10-19', sla: '2026-10-15' } }

const addDays = (iso: string, n: number): string => {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}
const isWorkday = (iso: string): boolean => ![0, 6].includes(new Date(`${iso}T12:00:00Z`).getUTCDay())
/** Working days after `from` up to and including `to`. */
function workdaysBetween(from: string, to: string): number {
  let n = 0
  for (let d = addDays(from, 1); d <= to; d = addDays(d, 1)) if (isWorkday(d)) n += 1
  return n
}

export interface TaskDetails {
  place: string
  date: string
}

export function boardAt(
  caseId: string,
  today: string,
  setStarted: boolean,
  phases: Record<string, TaskPhase>,
  details: Record<string, TaskDetails> = {},
): Board {
  const items = tasksAt(today, setStarted, phases)
  const done = (id: string) => items.find((x) => x.id === id)?.state === 'done'
  const wire: Array<{ task: TaskOut; effective: string }> = items.map((it) => {
    const dates = WIRE_DATES[it.id] ?? { due: it.due }
    const effective = dates.sla && dates.sla < dates.due ? dates.sla : dates.due
    const isDone = it.state === 'done'
    const overdueWorkdays = !isDone && effective < today ? workdaysBetween(effective, today) : 0
    const confirmed = details[it.id]
    const owner = { id: it.id, display: it.owner, role: LANE_ROLE[it.lane] }
    return {
      effective,
      task: {
        id: it.id,
        case_id: caseId,
        code: it.id,
        title: it.title,
        status: STATUS[it.phase],
        business_status: BUSINESS[it.phase],
        lane: LANE_ROLE[it.lane],
        owner,
        place: it.phase === 'to_order' ? null : (confirmed?.place ?? it.place),
        due: `${dates.due}T12:00:00+02:00`,
        sla_due: dates.sla ? `${dates.sla}T12:00:00+02:00` : null,
        scheduled_at: confirmed ? `${confirmed.date}T12:00:00+02:00` : null,
        escalated_at: overdueWorkdays > 0 ? `${addDays(effective, isWorkday(addDays(effective, 1)) ? 1 : 3)}T08:00:00+02:00` : null,
        overdue: overdueWorkdays > 0,
        overdue_workdays: overdueWorkdays,
        depends_on: it.dependsOn,
        blocked_by: it.dependsOn.filter((d) => !done(d)),
        ad_hoc: false,
        required_for_mdt: true,
        demo_assumption: true,
      },
    }
  })
  const open = wire.filter((w) => w.task.status !== 'completed' && w.task.blocked_by.length === 0).sort((a, b) => a.effective.localeCompare(b.effective))[0]
  const unordered = open?.task.business_status === 'objednano'
  return {
    case_id: caseId,
    computed_at: `${today}T09:00:00+02:00`,
    baton_holder: open
      ? {
          role: unordered ? 'coordinator' : open.task.lane,
          owner: unordered ? COORDINATOR : open.task.owner,
          task_id: open.task.id,
          task_title: open.task.title,
          basis: 'required_for_mdt',
          reason: unordered ? 'awaiting_confirmation' : 'action',
          due: open.task.due,
          demo_assumption: true,
        }
      : null,
    lanes: BOARD_ROLES.map((role) => ({ role, tasks: wire.filter((w) => w.task.lane === role).map((w) => w.task) })),
  }
}
