import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { buildReviewedSections } from '../fixtures/handover'
import { store } from '../fixtures/store'
import { problem, roleOf } from './util'

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export const handlers = [
  // Contract route `GET …/mdt-record?format=docx`: KOC team only; the file name carries NAVRH while a section is unconfirmed.
  http.get('/api/cases/:id/mdt-record', ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'coordinator' && role !== 'physician') return problem(403, 'Zápis může stáhnout pouze tým KOC')
    if (params.id !== ALENA_ID) return problem(404, 'Případ nebyl nalezen')
    const draft = buildReviewedSections(store.confirmed, store.edits).some((s) => !s.confirmed)
    return new HttpResponse(new Uint8Array([0x50, 0x4b, 0x03, 0x04]), {
      headers: {
        'Content-Type': DOCX,
        'Content-Disposition': `attachment; filename="MDT_zapis${draft ? '_NAVRH' : ''}.docx"`,
      },
    })
  }),
]
