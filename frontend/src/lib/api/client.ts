// Typed client generated from contracts/openapi.json (`pnpm gen:api`). Use it for every endpoint that is in the
// contract; `./http.ts` stays only for endpoints the contract does not describe yet.
import createClient from 'openapi-fetch'
import { getDemo } from '@/lib/demo'
import { ApiError } from './http'
import type { paths } from './schema'

export const client = createClient<paths>({
  baseUrl: window.location.origin,
  // Resolved per call so MSW (which patches fetch after import) sees the requests.
  fetch: (request) => globalThis.fetch(request),
})

// The demo clock is a query parameter the MSW mocks honour and the real backend ignores (it has its own clock).
client.use({
  onRequest({ request }) {
    const demo = getDemo()
    const url = new URL(request.url)
    if (!url.searchParams.has('today')) url.searchParams.set('today', demo.today)
    const forwarded = new Request(url, request)
    forwarded.headers.set('X-Demo-Role', demo.role === 'physician' ? 'koc_physician' : demo.role)
    return forwarded
  },
})

/** Unwraps an openapi-fetch result: data or a thrown `ApiError` carrying the problem+json title. */
export function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.data !== undefined) return r.data
  const title = (r.error as { title?: string } | undefined)?.title ?? 'Požadavek se nezdařil'
  throw new ApiError(r.response.status, title)
}
