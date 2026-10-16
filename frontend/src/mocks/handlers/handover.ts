import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { AS_OF_DEFAULT, DOCUMENTS } from '../fixtures/documents'
import { buildSections, CONFIRMABLE } from '../fixtures/handover'
import { store } from '../fixtures/store'
import { problem } from './util'

const CONFIRMER = 'MUDr. Havelka'

export const handlers = [
  http.get('/api/cases/:id/handover', ({ params, request }) => {
    if (params.id !== ALENA_ID) return HttpResponse.json({ asOf: AS_OF_DEFAULT, sections: [], excluded: [] })
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    return HttpResponse.json({
      asOf,
      sections: buildSections(store.confirmed),
      excluded: DOCUMENTS.filter((d) => new Date(d.received).getTime() > new Date(asOf).getTime()),
    })
  }),
  http.post('/api/cases/:id/handover/sections/:key/confirm', ({ params }) => {
    const key = String(params.key)
    const s = buildSections(store.confirmed).find((x) => x.key === key)
    if (!s) return problem(404, 'Sekce nebyla nalezena')
    if (!CONFIRMABLE(s)) return problem(409, 'Chybějící údaj nelze potvrdit')
    store.confirmed[key] = CONFIRMER
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/handover/confirm-all', () => {
    for (const s of buildSections(store.confirmed)) if (CONFIRMABLE(s)) store.confirmed[s.key] = CONFIRMER
    return HttpResponse.json({ ok: true })
  }),
]
