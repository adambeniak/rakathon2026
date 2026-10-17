import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setDemo } from '@/lib/demo'
import { server } from '@/mocks/server'
import { client, unwrap } from './client'
import { ApiError, api } from './http'
import { ApiProblem, problemFromBody } from './problem'
import { toApiRole } from './role'

function capture(path: string) {
  const seen: Request[] = []
  server.use(
    http.get(path, ({ request }) => {
      seen.push(request)
      return HttpResponse.json([])
    }),
  )
  return seen
}

afterEach(() => vi.unstubAllEnvs())

describe('toApiRole', () => {
  it('maps the UI physician to the backend Role value and passes the others through', () => {
    expect([
      toApiRole('physician'),
      toApiRole('gp'),
      toApiRole('coordinator'),
      toApiRole('reviewer'),
    ]).toEqual(['koc_physician', 'gp', 'coordinator', 'reviewer'])
  })
})

describe('demo headers on both HTTP clients', () => {
  it('sends X-Demo-Role: koc_physician for the physician role', async () => {
    setDemo({ role: 'physician', today: '2026-10-21' })
    const seen = capture('/api/cases')
    await client.GET('/api/cases')
    await api.get('/api/cases')
    expect(seen.map((r) => r.headers.get('x-demo-role'))).toEqual([
      'koc_physician',
      'koc_physician',
    ])
  })

  it('sends the demo date only to the mocks, never to the real backend', async () => {
    setDemo({ role: 'coordinator', today: '2026-10-19' })
    const mocked = capture('/api/cases')
    await client.GET('/api/cases')
    await api.get('/api/cases')
    expect(mocked.map((r) => new URL(r.url).searchParams.get('today'))).toEqual([
      '2026-10-19',
      '2026-10-19',
    ])

    vi.stubEnv('MODE', 'production')
    const live = capture('/api/cases')
    await client.GET('/api/cases')
    await api.get('/api/cases')
    expect(live.map((r) => new URL(r.url).search)).toEqual(['', ''])
  })
})

describe('problem+json', () => {
  const conflict = () =>
    HttpResponse.json(
      {
        type: 'about:blank',
        title: 'Hodnota sekce se mezitím změnila',
        status: 409,
        detail: 'hash mismatch',
      },
      { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
    )

  it('is thrown by the generated client as a typed ApiProblem', async () => {
    server.use(http.get('/api/cases', conflict))
    const error = await client.GET('/api/cases').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiProblem)
    expect(error).toMatchObject({
      status: 409,
      title: 'Hodnota sekce se mezitím změnila',
      detail: 'hash mismatch',
    })
  })

  it('is the same class the legacy client throws, so existing instanceof ApiError checks keep working', async () => {
    server.use(http.get('/api/cases', conflict))
    const error = await api.get('/api/cases').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toBeInstanceOf(ApiProblem)
    expect(error).toMatchObject({ status: 409, title: 'Hodnota sekce se mezitím změnila' })
  })

  it('keeps code and blocking_items for programs; a malformed field is dropped, the rest kept', async () => {
    server.use(
      http.get('/api/cases', () =>
        HttpResponse.json(
          {
            title: 'Podmínky akce nejsou splněny',
            status: 409,
            detail: 'Připravenost k MDT není splněna, chybí: performance_status',
            code: 'guard_failed',
            blocking_items: ['performance_status'],
          },
          { status: 409, headers: { 'Content-Type': 'application/problem+json' } },
        ),
      ),
    )
    await expect(client.GET('/api/cases')).rejects.toMatchObject({
      status: 409,
      code: 'guard_failed',
      blockingItems: ['performance_status'],
    })
    const malformed = problemFromBody(409, {
      title: 'Podmínky akce nejsou splněny',
      code: 'guard_failed',
      blocking_items: 'performance_status',
    })
    expect(malformed).toMatchObject({
      title: 'Podmínky akce nejsou splněny',
      code: 'guard_failed',
      blockingItems: undefined,
    })
  })

  it('falls back to a neutral title when the body is not problem+json', async () => {
    server.use(
      http.get('/api/cases', () => new HttpResponse('<html>bad gateway</html>', { status: 502 })),
    )
    await expect(client.GET('/api/cases')).rejects.toMatchObject({
      status: 502,
      title: 'Požadavek se nezdařil',
    })
  })

  it('unwrap returns data and throws a problem for an empty result', () => {
    expect(unwrap({ data: [1], response: new Response() })).toEqual([1])
    expect(() => unwrap({ response: new Response(null, { status: 500 }) })).toThrow(ApiProblem)
  })
})
