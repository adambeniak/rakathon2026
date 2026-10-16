import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { AS_OF_DEFAULT } from '../fixtures/documents'
import { buildReviewedSections, buildSections, CONFIRMABLE, sectionHash } from '../fixtures/handover'
import { emptyWire, toWire } from '../fixtures/handoverWire'
import { store } from '../fixtures/store'
import { DEMO_USERS } from '../fixtures/people'
import { problem, roleOf } from './util'


export const handlers = [
  // Wire shape of the contract (`Handover`); the UI adapts it with `adaptHandover`.
  http.get('/api/cases/:id/handover', ({ params, request }) => {
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    if (params.id !== ALENA_ID) return HttpResponse.json(emptyWire(String(params.id), asOf))
    return HttpResponse.json(toWire(ALENA_ID, asOf, buildSections(store.confirmed, asOf), store.edits))
  }),
  // Contract route: by section number, with the hash of the value the physician saw.
  http.post('/api/cases/:id/handover/sections/:number/confirm', async ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může potvrdit pouze lékař')
    const s = buildReviewedSections(store.confirmed, store.edits).find((x) => x.number === Number(params.number))
    if (!s) return problem(404, 'Sekce nebyla nalezena')
    const body = (await request.json().catch(() => ({}))) as { expected_value_hash?: string }
    if (!body.expected_value_hash) return problem(422, 'Chybí kontrolní otisk hodnoty sekce')
    if (body.expected_value_hash !== sectionHash(s)) return problem(409, 'Hodnota sekce se mezitím změnila')
    if (!CONFIRMABLE(s)) return problem(409, 'Chybějící údaj nelze potvrdit')
    store.confirmed[s.key] = DEMO_USERS[role].name
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/handover/sections/:key/edit', async ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může upravit pouze lékař')
    const body = (await request.json()) as { rows?: Record<number, string>; reason?: string }
    if (!body.reason?.trim()) return problem(422, 'Uveďte důvod změny')
    const key = String(params.key)
    if (!buildSections(store.confirmed).some((x) => x.key === key)) return problem(404, 'Sekce nebyla nalezena')
    const by = DEMO_USERS[role].name
    const at = new Date().toLocaleString('cs-CZ', { timeZone: 'Europe/Prague' })
    const reason = body.reason.trim()
    const rowEdits = (store.edits[key] ??= {})
    for (const [i, value] of Object.entries(body.rows ?? {})) rowEdits[Number(i)] = { value, reason, by, at }
    delete store.confirmed[key] // an edited value must be confirmed again
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/handover/confirm-all', ({ request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může potvrdit pouze lékař')
    for (const s of buildSections(store.confirmed)) if (CONFIRMABLE(s)) store.confirmed[s.key] = DEMO_USERS[role].name
    return HttpResponse.json({ ok: true })
  }),
]
