import { http, HttpResponse } from 'msw'
import { allCases } from '../fixtures/cases'
import { KOC_DIRECTORY } from '../fixtures/people'
import { store } from '../fixtures/store'
import { todayOf } from './util'

export const handlers = [
  http.get('/api/gp/cases', ({ request }) =>
    HttpResponse.json(allCases(todayOf(request), store).filter((c) => c.gp === 'MUDr. Řezníček')),
  ),
  http.get('/api/reviewer/cases', ({ request }) =>
    HttpResponse.json(allCases(todayOf(request), store).filter((c) => c.insurer.startsWith('211'))),
  ),
  http.get('/api/koc', () => HttpResponse.json(KOC_DIRECTORY)),
  http.post('/api/referrals/parse', async ({ request }) => {
    const body = (await request.json()) as { filename?: string }
    return HttpResponse.json({
      filename: body.filename ?? 'zadost.pdf',
      patientName: 'Alena Procházková',
      birthDate: '1963-07-22',
      birthNumber: '635722/1013',
      insurer: '211 – Zdravotní pojišťovna ministerstva vnitra ČR',
      diagnosis: 'C25.0 – suspektní tumor hlavy pankreatu',
      urgent: true,
      evidence: { docId: '07_PL_zadost_KOC2_2026-10-02', quote: 'C25.0 – suspektní tumor hlavy pankreatu' },
    })
  }),
  http.post('/api/referrals', () => HttpResponse.json({ caseId: 'rakathon-2026-prochazkova', state: 'sent' }, { status: 201 })),
]
