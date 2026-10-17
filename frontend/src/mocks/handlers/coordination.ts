// Mock endpoints for demo step 4 on the contract paths: pathway launch, board, task transitions.
import { http, HttpResponse } from 'msw'
import type { components } from '@/lib/api/schema'
import type { TaskPhase } from '@/lib/domain'
import { ALENA_ID } from '../fixtures/cases'
import { store } from '../fixtures/store'
import { boardAt, tasksAt, type TaskDetails } from '../fixtures/tasks'
import { problem, roleOf, todayOf } from './util'

type Transition = components['schemas']['app__api__schemas__coordination__TransitionRequest']
type Launch = components['schemas']['LaunchPathwayRequest']

const ORDER: TaskPhase[] = ['to_order', 'ordered', 'performed', 'result_delivered']
const NEXT_EVENT: Record<string, TaskPhase> = { confirm: 'ordered', perform: 'performed', deliver_result: 'result_delivered' }

// Place and date the coordinator confirmed per task; cleared when the pathway is launched again (store reset).
let confirmed: Record<string, TaskDetails> = {}

export const handlers = [
  http.get('/api/cases/:id/board', ({ params, request }) => {
    const id = String(params.id)
    if (id !== ALENA_ID) return problem(404, 'Případ nebyl nalezen')
    return HttpResponse.json(boardAt(id, todayOf(request), store.setStarted, store.taskPhase, confirmed))
  }),
  http.post('/api/cases/:id/pathways', async ({ params, request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Sadu může spustit pouze koordinátorka')
    if (params.id !== ALENA_ID) return problem(404, 'Případ nebyl nalezen')
    const body = (await request.json()) as Partial<Launch>
    if (!body.indicated_by) return problem(422, 'Sada vyšetření vyžaduje indikujícího lékaře KOC.')
    if (!body.mdt_start) return problem(422, 'Případ nemá plánovaný začátek MDT.')
    if (store.setStarted) return problem(409, 'Sada už byla spuštěna')
    store.setStarted = true
    confirmed = {}
    const board = boardAt(ALENA_ID, todayOf(request), true, store.taskPhase, confirmed)
    const tasks = board.lanes.flatMap((l) => l.tasks)
    const owner = { id: body.indicated_by, display: body.indicated_by, role: 'koc_physician' as const }
    return HttpResponse.json(
      { plan_url: body.plan_url, start_date: body.start_date, indicated_by: owner, tasks, baton_holder: board.baton_holder },
      { status: 201 },
    )
  }),
  http.post('/api/tasks/:taskId/transitions', async ({ params, request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Stav úkolu může měnit pouze koordinátorka')
    const body = (await request.json()) as Partial<Transition>
    const today = todayOf(request)
    const tasks = tasksAt(today, store.setStarted, store.taskPhase)
    const task = tasks.find((t) => t.id === params.taskId)
    if (!task) return problem(404, 'Úkol nebyl nalezen')
    const target = body.event ? NEXT_EVENT[body.event] : undefined
    if (!target || ORDER.indexOf(target) !== ORDER.indexOf(task.phase) + 1)
      return problem(409, 'Úkol nelze přesunout do tohoto stavu')
    const blocker = task.dependsOn.map((d) => tasks.find((t) => t.id === d)).find((d) => d && d.state !== 'done')
    if (blocker) return problem(409, `Úkol čeká na: ${blocker.title}`)
    if (body.event === 'confirm') {
      if (!body.place?.trim() || !body.date) return problem(422, 'Potvrzení objednání vyžaduje pracoviště a datum')
      confirmed[task.id] = { place: body.place.trim(), date: body.date.slice(0, 10) }
    }
    if (body.event === 'deliver_result' && !body.document_id) return problem(422, 'Doručení výsledku vyžaduje dokument')
    store.taskPhase[task.id] = target
    const out = boardAt(ALENA_ID, today, store.setStarted, store.taskPhase, confirmed)
      .lanes.flatMap((l) => l.tasks)
      .find((t) => t.id === task.id)
    return HttpResponse.json(body.event === 'deliver_result' ? { ...out, result_doc_id: body.document_id } : out)
  }),
]
