// Case list and detail, claim/acknowledge, and the triage document requests (demo steps 1–2).
// The document requests are not in contracts/openapi.json yet: paths and payloads are provisional.
import { http, HttpResponse } from 'msw'
import type { DocumentRequest } from '@/lib/domain'
import { toApiCase, toApiDetail } from '../fixtures/api'
import { ALENA_ID, allCases, caseById, inboxCases, newStore } from '../fixtures/cases'
import { DOCUMENTS } from '../fixtures/documents'
import { activeFindings } from '../fixtures/findings'
import { AUDIT, MESSAGES } from '../fixtures/messages'
import { store } from '../fixtures/store'
import { timelineAt } from '../fixtures/timeline'
import { problem, roleOf, todayOf } from './util'

const isAlena = (id: string | readonly string[] | undefined) => id === ALENA_ID

// Verbatim line from report 07 (the list of examinations the GP refers to); the API returns it with each proposal.
const REFERRAL_EVIDENCE = {
  docId: '07_PL_zadost_KOC2_2026-10-02',
  quote: 'UZ břicha 29. 9. 2026 (RDG pracoviště, Poliklinika Jižní)',
}

/** Reports 01–06 are referenced by the GP's request but not attached (demo step 2). */
function proposals(today: string): DocumentRequest[] {
  return DOCUMENTS.slice(0, 6).filter((d) => d.received.slice(0, 10) > today).map((d) => ({
    id: `req-${d.id}`,
    title: d.title,
    recipient: d.place,
    docId: d.id,
    requested: store.requested.includes(`req-${d.id}`),
    evidence: REFERRAL_EVIDENCE,
  }))
}

export const handlers = [
  http.get('/api/cases', ({ request }) => HttpResponse.json(inboxCases(todayOf(request), store).map((c) => toApiCase(c, todayOf(request))))),
  http.get('/api/cases/:id', ({ params, request }) => {
    const c = caseById(String(params.id), todayOf(request), store)
    return c ? HttpResponse.json(toApiDetail(c, todayOf(request))) : problem(404, 'Případ nebyl nalezen')
  }),
  http.get('/api/cases/:id/findings', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? activeFindings(todayOf(request)) : []),
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
  http.get('/api/cases/:id/document-requests', ({ params, request }) =>
    HttpResponse.json(params.id === ALENA_ID ? proposals(todayOf(request)) : []),
  ),
  http.post('/api/cases/:id/document-requests', async ({ request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Podklady může vyžádat pouze koordinátorka')
    const body = (await request.json()) as { ids?: string[] }
    const valid = new Set(proposals(todayOf(request)).map((p) => p.id))
    const ids = (body.ids ?? []).filter((i) => valid.has(i))
    if (ids.length === 0) return problem(422, 'Vyberte alespoň jeden dokument')
    for (const id of ids) if (!store.requested.includes(id)) store.requested.push(id)
    return HttpResponse.json({ requested: ids.length })
  }),
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
    Object.assign(store, newStore())
    return HttpResponse.json({ ok: true, cases: allCases('2026-10-16', store).length })
  }),
]
