// Mock of the document upload (`POST /api/cases/{case_id}/documents`, contract `DocumentReceived`). The list itself is
// part of `GET /api/cases/:id` (handlers/cases.ts); the mock does not add the file to it, it only validates the request.
import { http, HttpResponse } from 'msw'
import { toApiCase } from '../fixtures/api'
import { caseById } from '../fixtures/cases'
import { store } from '../fixtures/store'
import { problem, roleOf, todayOf } from './util'

const SUPPORTED = /\.(pdf|docx)$/i
const DATE_IN_NAME = /(\d{4}-\d{2}-\d{2})/

export const handlers = [
  http.post('/api/cases/:id/documents', async ({ params, request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Zprávu může přidat pouze koordinátorka')
    const today = todayOf(request)
    const c = caseById(String(params.id), today, store)
    if (!c) return problem(404, 'Případ nebyl nalezen')
    const form = await request.formData().catch(() => null)
    const file = form?.get('file')
    if (!(file instanceof File)) return problem(422, 'Chybí soubor se zprávou')
    if (!SUPPORTED.test(file.name)) return problem(422, 'Podporovány jsou pouze soubory PDF a DOCX')
    const stem = file.name.replace(SUPPORTED, '')
    const authored = String(form?.get('authored_at') ?? '') || DATE_IN_NAME.exec(stem)?.[1] || today
    return HttpResponse.json(
      {
        document: { doc_id: stem, title: stem, authored_at: authored, received_at: `${today}T09:00:00+02:00` },
        open_requests_remaining: 0,
        case: toApiCase(c, today),
      },
      { status: 201 },
    )
  }),
]
