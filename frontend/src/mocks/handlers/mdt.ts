import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { AS_OF_DEFAULT } from '../fixtures/documents'
import { buildSections } from '../fixtures/handover'
import { buildMdt } from '../fixtures/mdt'
import { store } from '../fixtures/store'
import { problem } from './util'

export const handlers = [
  http.get('/api/cases/:id/mdt', ({ params, request }) => {
    if (params.id !== ALENA_ID) return problem(404, 'MDT podklady nejsou k dispozici')
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    const sections = buildSections(store.confirmed)
    return HttpResponse.json({ ...buildMdt(asOf, sections, store.mdtGeneratedAt), sections })
  }),
  http.post('/api/cases/:id/send-feedback', () => {
    if (!store.mdtGeneratedAt) return problem(409, 'Nejprve vygenerujte MDT zápis')
    store.feedbackSent = true
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/mdt/generate', ({ request }) => {
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    const view = buildMdt(asOf, buildSections(store.confirmed), null)
    if (!view.ready) return problem(409, 'Podmínky připravenosti nejsou splněny')
    store.mdtGeneratedAt = asOf
    return HttpResponse.json({ ok: true, generatedAt: asOf })
  }),
]
