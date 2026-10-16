import { http, HttpResponse } from 'msw'
import { toApiCase, toApiDetail } from '../fixtures/api'
import { ALENA_ID, allCases, caseById, inboxCases } from '../fixtures/cases'
import { activeFindings } from '../fixtures/findings'
import { AUDIT, MESSAGES } from '../fixtures/messages'
import { store } from '../fixtures/store'
import { tasksAt } from '../fixtures/tasks'
import { timelineAt } from '../fixtures/timeline'
import { problem, todayOf } from './util'

const isAlena = (id: string | readonly string[] | undefined) => id === ALENA_ID

export const handlers = [
  http.get('/api/cases', ({ request }) => HttpResponse.json(inboxCases(todayOf(request), store).map((c) => toApiCase(c, todayOf(request))))),
  http.get('/api/cases/:id', ({ params, request }) => {
    const c = caseById(String(params.id), todayOf(request), store)
    return c ? HttpResponse.json(toApiDetail(c, todayOf(request))) : problem(404, 'Případ nebyl nalezen')
  }),
  http.get('/api/cases/:id/findings', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? activeFindings(todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/tasks', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? tasksAt(todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/timeline', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? timelineAt(todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/messages', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? MESSAGES.filter((m) => m.at.slice(0, 10) <= todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/audit', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? AUDIT.filter((a) => a.at.slice(0, 10) <= todayOf(request)) : []),
  ),
  http.post('/api/cases/:id/claim', ({ params }) => {
    const id = String(params.id)
    if (!store.claimed.includes(id)) store.claimed.push(id)
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/acknowledge', ({ params }) => {
    const id = String(params.id)
    if (!store.acknowledged.includes(id)) store.acknowledged.push(id)
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/mock/reset', () => {
    Object.assign(store, { claimed: [], acknowledged: [], feedbackSent: false, mdtGeneratedAt: null, confirmed: {}, extraCases: [] })
    return HttpResponse.json({ ok: true, cases: allCases('2026-10-16', store).length })
  }),
]
