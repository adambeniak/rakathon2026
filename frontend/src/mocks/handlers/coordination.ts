// Mock endpoints for demo step 4 (task set, task board).
// Not in contracts/openapi.json yet: paths and payloads are provisional and live only here and in the feature api.ts.
import { http, HttpResponse } from 'msw'
import type { TaskPhase } from '@/lib/domain'
import { ALENA_ID } from '../fixtures/cases'
import { store } from '../fixtures/store'
import { tasksAt } from '../fixtures/tasks'
import { problem, roleOf, todayOf } from './util'

const ORDER: TaskPhase[] = ['to_order', 'ordered', 'performed', 'result_delivered']

export const handlers = [
  http.get('/api/cases/:id/tasks', ({ params, request }) =>
    HttpResponse.json(
      params.id === ALENA_ID ? tasksAt(todayOf(request), store.setStarted, store.taskPhase) : [],
    ),
  ),
  http.post('/api/cases/:id/task-sets', ({ params, request }) => {
    if (roleOf(request) !== 'coordinator')
      return problem(403, 'Sadu může spustit pouze koordinátorka')
    if (params.id !== ALENA_ID) return problem(404, 'Sada úkolů pro tento případ není k dispozici')
    store.setStarted = true
    return HttpResponse.json({ started: true })
  }),
  http.post('/api/cases/:id/tasks/:taskId/phase', async ({ params, request }) => {
    if (roleOf(request) !== 'coordinator')
      return problem(403, 'Stav úkolu může měnit pouze koordinátorka')
    const { phase } = (await request.json()) as { phase?: TaskPhase }
    const tasks = tasksAt(todayOf(request), store.setStarted, store.taskPhase)
    const task = tasks.find((t) => t.id === params.taskId)
    if (!task) return problem(404, 'Úkol nebyl nalezen')
    if (!phase || ORDER.indexOf(phase) !== ORDER.indexOf(task.phase) + 1)
      return problem(409, 'Úkol nelze přesunout do tohoto stavu')
    const blocker = task.dependsOn
      .map((d) => tasks.find((t) => t.id === d))
      .find((d) => d && d.state !== 'done')
    if (blocker) return problem(409, `Úkol čeká na: ${blocker.title}`)
    store.taskPhase[task.id] = phase
    return HttpResponse.json({ ok: true })
  }),
]
