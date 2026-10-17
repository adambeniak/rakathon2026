// Case lists of the GP and reviewer portals.
import { http, HttpResponse } from 'msw'
import { allCases } from '../fixtures/cases'
import { store } from '../fixtures/store'
import { todayOf } from './util'

export const handlers = [
  http.get('/api/gp/cases', ({ request }) =>
    HttpResponse.json(allCases(todayOf(request), store).filter((c) => c.gp === 'MUDr. Řezníček')),
  ),
  http.get('/api/reviewer/cases', ({ request }) =>
    HttpResponse.json(
      allCases(todayOf(request), store).filter((c) => c.insurer?.startsWith('211')),
    ),
  ),
]
