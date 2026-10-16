// Mock endpoints for demo steps 2 and 4 (triage document requests, task set, task board).
// Not in contracts/openapi.json yet: paths and payloads are provisional and live only here and in the feature api.ts.
import { http, HttpResponse } from 'msw'
import type { DocumentRequest, TaskPhase } from '@/lib/domain'
import { ALENA_ID } from '../fixtures/cases'
import { DOCUMENTS } from '../fixtures/documents'
import { store } from '../fixtures/store'
import { tasksAt } from '../fixtures/tasks'
import { problem, roleOf, todayOf } from './util'

const ORDER: TaskPhase[] = ['to_order', 'ordered', 'performed', 'result_delivered']

/** Reports 01–06 are referenced by the GP's request but not attached (demo step 2). */
function proposals(): DocumentRequest[] {
  return DOCUMENTS.slice(0, 6).map((d) => ({
    id: `req-${d.id}`,
    title: d.title,
    recipient: d.place,
    docId: d.id,
    requested: store.requested.includes(`req-${d.id}`),
  }))
}

export const handlers = [
  http.get('/api/cases/:id/document-requests', ({ params }) =>
    HttpResponse.json(params.id === ALENA_ID ? proposals() : []),
  ),
  http.post('/api/cases/:id/document-requests', async ({ request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Podklady může vyžádat pouze koordinátorka')
    const body = (await request.json()) as { ids?: string[] }
    const valid = new Set(proposals().map((p) => p.id))
    const ids = (body.ids ?? []).filter((i) => valid.has(i))
    if (ids.length === 0) return problem(422, 'Vyberte alespoň jeden dokument')
    for (const id of ids) if (!store.requested.includes(id)) store.requested.push(id)
    return HttpResponse.json({ requested: ids.length })
  }),
  http.get('/api/cases/:id/tasks', ({ params, request }) =>
    HttpResponse.json(params.id === ALENA_ID ? tasksAt(todayOf(request), store.setStarted, store.taskPhase) : []),
  ),
  http.post('/api/cases/:id/task-sets', ({ request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Sadu může spustit pouze koordinátorka')
    store.setStarted = true
    return HttpResponse.json({ started: true })
  }),
  http.post('/api/cases/:id/tasks/:taskId/phase', async ({ params, request }) => {
    const { phase } = (await request.json()) as { phase?: TaskPhase }
    const tasks = tasksAt(todayOf(request), store.setStarted, store.taskPhase)
    const task = tasks.find((t) => t.id === params.taskId)
    if (!task) return problem(404, 'Úkol nebyl nalezen')
    if (!phase || ORDER.indexOf(phase) !== ORDER.indexOf(task.phase) + 1) return problem(409, 'Úkol nelze přesunout do tohoto stavu')
    const blocker = task.dependsOn.map((d) => tasks.find((t) => t.id === d)).find((d) => d && d.state !== 'done')
    if (blocker) return problem(409, `Úkol čeká na: ${blocker.title}`)
    store.taskPhase[task.id] = phase
    return HttpResponse.json({ ok: true })
  }),
]
