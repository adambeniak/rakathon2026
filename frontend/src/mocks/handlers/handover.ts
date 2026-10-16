import { http, HttpResponse } from 'msw'
import { ALENA_ID } from '../fixtures/cases'
import { AS_OF_DEFAULT, DOCUMENTS } from '../fixtures/documents'
import { buildSections, CONFIRMABLE } from '../fixtures/handover'
import { store } from '../fixtures/store'
import { DEMO_USERS } from '../fixtures/people'
import { problem, roleOf } from './util'


export const handlers = [
  http.get('/api/cases/:id/handover', ({ params, request }) => {
    if (params.id !== ALENA_ID) return HttpResponse.json({ asOf: AS_OF_DEFAULT, sections: [], excluded: [] })
    const asOf = new URL(request.url).searchParams.get('as_of') ?? AS_OF_DEFAULT
    return HttpResponse.json({
      asOf,
      sections: buildSections(store.confirmed, asOf).map((s) => {
        const edit = store.edits[s.key]
        if (!edit) return s
        return {
          ...s,
          rows: s.rows.map((r, i) =>
            edit.rows[i] === undefined ? r : { ...r, value: edit.rows[i], note: `Upraveno: ${edit.reason} (${edit.by})` },
          ),
        }
      }),
      excluded: DOCUMENTS.filter((d) => new Date(d.received).getTime() > new Date(asOf).getTime()),
    })
  }),
  http.post('/api/cases/:id/handover/sections/:key/confirm', ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může potvrdit pouze lékař')
    const key = String(params.key)
    const s = buildSections(store.confirmed).find((x) => x.key === key)
    if (!s) return problem(404, 'Sekce nebyla nalezena')
    if (!CONFIRMABLE(s)) return problem(409, 'Chybějící údaj nelze potvrdit')
    store.confirmed[key] = DEMO_USERS[role].name
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/handover/sections/:key/edit', async ({ params, request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může upravit pouze lékař')
    const body = (await request.json()) as { rows?: Record<number, string>; reason?: string }
    if (!body.reason?.trim()) return problem(422, 'Uveďte důvod změny')
    const key = String(params.key)
    if (!buildSections(store.confirmed).some((x) => x.key === key)) return problem(404, 'Sekce nebyla nalezena')
    store.edits[key] = { rows: { ...store.edits[key]?.rows, ...body.rows }, reason: body.reason.trim(), by: DEMO_USERS[role].name }
    delete store.confirmed[key] // an edited value must be confirmed again
    return HttpResponse.json({ ok: true })
  }),
  http.post('/api/cases/:id/handover/confirm-all', ({ request }) => {
    const role = roleOf(request)
    if (role !== 'physician') return problem(403, 'Sekci může potvrdit pouze lékař')
    for (const s of buildSections(store.confirmed)) if (CONFIRMABLE(s)) store.confirmed[s.key] = DEMO_USERS[role].name
    return HttpResponse.json({ ok: true })
  }),
]
