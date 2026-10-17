import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { AS_OF_DEFAULT } from '../fixtures/documents'
import { buildReviewedSections, buildSections, sectionHash } from '../fixtures/handover'
import { acceptedMissing, emptyWire, toWire } from '../fixtures/handoverWire'
import { store } from '../fixtures/store'
import { DEMO_USERS } from '../fixtures/people'
import { problem, roleOf } from './util'

/** The sections whose `value` is a plain string; `edited_value` of any other section is refused like the API does. */
const TEXT_SECTIONS = new Set(['5_mdt_question', '8_allergies'])

const wire = (asOf: string) => toWire(ALENA_ID, asOf, buildSections(store.confirmed, asOf), store.edits, acceptedMissing(store.confirmed))

export const handlers = [
  // Wire shape of the contract (`Handover`); the UI adapts it with `adaptHandover`.
  http.get('/api/cases/:id/handover', ({ params, request }) => {
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    if (params.id !== ALENA_ID) return HttpResponse.json(emptyWire(String(params.id), asOf))
    return HttpResponse.json(wire(asOf))
  }),
  // Contract route `POST …/handover`: stores the snapshot (idempotent) and answers like the GET above.
  http.post('/api/cases/:id/handover', ({ params, request }) => {
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    if (params.id !== ALENA_ID) return HttpResponse.json(emptyWire(String(params.id), asOf))
    return HttpResponse.json(wire(asOf))
  }),
  // Contract route `POST …/sections/{number}/confirm` (body `ConfirmSection`, answer: the whole `Handover`).
  // Confirmation is per section only: there is no bulk route.
  http.post('/api/cases/:id/handover/sections/:number/confirm', async ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může potvrdit pouze lékař')
    const s = buildReviewedSections(store.confirmed, store.edits).find((x) => x.number === Number(params.number))
    if (!s) return problem(404, 'Sekce nebyla nalezena')
    const body = (await request.json().catch(() => ({}))) as { expected_value_hash?: string; accept_missing?: boolean; edited_value?: unknown }
    if (!body.expected_value_hash) return problem(422, 'Chybí kontrolní otisk hodnoty sekce')
    if (body.expected_value_hash !== sectionHash(s)) return problem(409, 'Hodnota sekce se mezitím změnila')
    const missing = s.status === 'missing'
    const edited = body.edited_value !== undefined && body.edited_value !== null
    if (body.accept_missing && edited) return problem(422, 'Použijte buď upravenou hodnotu, nebo přijetí chybějícího')
    if (body.accept_missing && !missing) return problem(409, 'Sekce není chybějící; potvrďte ji nebo upravte')
    if (missing && !body.accept_missing && !edited) return problem(409, 'Chybějící sekci lze jen přijmout jako chybějící nebo doplnit')
    if (edited && (!TEXT_SECTIONS.has(s.key) || typeof body.edited_value !== 'string' || body.edited_value.trim() === '')) {
      return problem(422, 'Upravená hodnota neodpovídá sekci')
    }
    const by = DEMO_USERS[role].name
    if (edited) {
      const at = new Date().toLocaleString('cs-CZ', { timeZone: 'Europe/Prague' })
      store.edits[s.key] = { 0: { value: String(body.edited_value).trim(), reason: '', by, at } }
    }
    if (body.accept_missing) acceptedMissing(store.confirmed).add(s.key)
    store.confirmed[s.key] = by
    return HttpResponse.json(wire(AS_OF_DEFAULT))
  }),
]
