import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { buildReviewedSections } from '../fixtures/handover'
import { store } from '../fixtures/store'
import { problem, roleOf } from './util'

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const PDF = 'application/pdf'
// The first bytes of each format; enough for the browser to save a file of the right type.
const MAGIC = { docx: [0x50, 0x4b, 0x03, 0x04], pdf: [0x25, 0x50, 0x44, 0x46, 0x2d] } as const

export const handlers = [
  // Contract route `GET …/mdt-record?format=docx|pdf`: KOC team only; the file name carries NAVRH while a section is
  // unconfirmed. Any other format is refused like the API's query validation (422).
  http.get('/api/cases/:id/mdt-record', ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'coordinator' && role !== 'physician')
      return problem(403, 'Zápis může stáhnout pouze tým KOC')
    if (params.id !== ALENA_ID) return problem(404, 'Případ nebyl nalezen')
    const format = new URL(request.url).searchParams.get('format') ?? 'docx'
    if (format !== 'docx' && format !== 'pdf') return problem(422, 'Neplatný formát zápisu')
    const draft = buildReviewedSections(store.confirmed, store.edits).some((s) => !s.confirmed)
    return new HttpResponse(new Uint8Array(MAGIC[format]), {
      headers: {
        'Content-Type': format === 'pdf' ? PDF : DOCX,
        'Content-Disposition': `attachment; filename="MDT_zapis${draft ? '_NAVRH' : ''}.${format}"`,
      },
    })
  }),
]
