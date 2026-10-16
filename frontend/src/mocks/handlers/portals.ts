import { http, HttpResponse } from 'msw'
import { allCases } from '../fixtures/cases'
import { documentById } from '../fixtures/documents'
import { KOC_DIRECTORY } from '../fixtures/people'
import { store } from '../fixtures/store'
import { todayOf } from './util'

// Quotes are taken verbatim from the golden file.
function ev(docId: string, quote: string) {
  return { docId, quote, doc: documentById(docId) }
}

export const handlers = [
  http.get('/api/gp/cases', ({ request }) =>
    HttpResponse.json(allCases(todayOf(request), store).filter((c) => c.gp === 'MUDr. Řezníček')),
  ),
  http.get('/api/reviewer/cases', ({ request }) =>
    HttpResponse.json(allCases(todayOf(request), store).filter((c) => c.insurer?.startsWith('211'))),
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
      evidence: {
        patientName: ev('08_CT_KOC1_2026-10-08', 'Alena Procházková, RČ 635722/1013, ZP 211'),
        birthNumber: ev('08_CT_KOC1_2026-10-08', 'Alena Procházková, RČ 635722/1013, ZP 211'),
        insurer: ev('08_CT_KOC1_2026-10-08', 'Alena Procházková, RČ 635722/1013, ZP 211'),
        birthDate: ev('07_PL_zadost_KOC2_2026-10-02', '22. 7. 1963 (63 let)'),
        diagnosis: ev('07_PL_zadost_KOC2_2026-10-02', 'C25.0 – suspektní tumor hlavy pankreatu'),
        urgent: ev('07_PL_zadost_KOC2_2026-10-02', 'prosím o urgentní řešení'),
      },
    })
  }),
  http.post('/api/referrals', () => HttpResponse.json({ caseId: 'rakathon-2026-prochazkova', state: 'odeslano' }, { status: 201 })),
]
