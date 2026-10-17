// Portal endpoints on contract paths: the signed MDT conclusion the GP opens and the insurer reviewer's case list.
import { http, HttpResponse } from 'msw'
import type { components } from '@/lib/api/schema'
import { toReviewerCase } from '../fixtures/api'
import { ALENA_ID, allCases } from '../fixtures/cases'
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
    // A conclusion signed through the transitions mock wins over the seeded one.
    const signed = c.id === ALENA_ID ? store.conclusion : null
    const visible = roleOf(request) !== 'gp' || SENT.has(c.state)
    if (signed && visible) {
      return HttpResponse.json({
        text: signed.text,
        signed_by: { id: 'hruby-pavel@koc2-nemocnice-lipova', display: signed.by, role: 'koc_physician' },
        signed_at: signed.signedAt,
      })
    }
    if (SENT.has(c.state)) return HttpResponse.json(CONCLUSION)
    return roleOf(request) === 'gp'
      ? problem(403, 'Zpětná vazba ještě nebyla odeslána')
      : problem(404, 'Závěr MDT nebyl nalezen')
  }),
  // Like the backend: only the reviewer role, only the reviewer's insurer (the seeded reviewer is from ZP 211).
  http.get('/api/reviewer/cases', ({ request }) => {
    if (roleOf(request) !== 'reviewer') return problem(403, 'Přehled pro pojišťovnu je určen jen revizním lékařům')
    const own = allCases(todayOf(request), store).filter((c) => c.insurer.startsWith('211'))
    return HttpResponse.json(own.map(toReviewerCase))
  }),
]
