// Insurer analytics (simulated cohort): like the backend, only the insurer's reviewer may read it.
import { http, HttpResponse } from 'msw'
import { INSURER_ANALYTICS } from '../fixtures/insurer'
import { problem, roleOf } from './util'

export const handlers = [
  http.get('/api/insurer/analytics', ({ request }) =>
    roleOf(request) === 'reviewer'
      ? HttpResponse.json(INSURER_ANALYTICS)
      : problem(403, 'Analytika péče je dostupná jen reviznímu lékaři zdravotní pojišťovny'),
  ),
]
