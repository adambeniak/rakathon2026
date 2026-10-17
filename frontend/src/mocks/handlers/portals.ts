// Portal endpoints: the signed MDT conclusion the GP opens (contract path) and the reviewer's case list (provisional).
import { http, HttpResponse } from 'msw'
import type { components } from '@/lib/api/schema'
import { allCases } from '../fixtures/cases'
import { store } from '../fixtures/store'
import { problem, roleOf, todayOf } from './util'

const SENT = new Set(['zpetna_vazba_odeslana', 'uzavreno'])

const CONCLUSION: components['schemas']['MdtConclusionOut'] = {
  text: 'Závěr MDT: postup dle zápisu z jednání ze dne 21. 10. 2026.',
  signed_by: {
    id: 'markova-lenka@koc2-nemocnice-lipova',
    display: 'MUDr. Lenka Marková',
    role: 'koc_physician',
  },
  signed_at: '2026-10-21T09:30:00+02:00',
}

export const handlers = [
  // Like the backend: the referring GP reads the conclusion only once the feedback was sent to them.
  http.get('/api/cases/:id/mdt-conclusion', ({ params, request }) => {
    const c = allCases(todayOf(request), store).find((x) => x.id === params.id)
    if (!c) return problem(404, 'Případ nebyl nalezen')
    if (SENT.has(c.state)) return HttpResponse.json(CONCLUSION)
    return roleOf(request) === 'gp'
      ? problem(403, 'Zpětná vazba ještě nebyla odeslána')
      : problem(404, 'Závěr MDT nebyl nalezen')
  }),
  http.get('/api/reviewer/cases', ({ request }) =>
    HttpResponse.json(
      allCases(todayOf(request), store).filter((c) => c.insurer?.startsWith('211')),
    ),
  ),
]
