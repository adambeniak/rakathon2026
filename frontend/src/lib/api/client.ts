// The one HTTP client: generated from contracts/openapi.json (`pnpm gen:api`). Use it for every endpoint that is in
// the contract; `./http.ts` stays only for endpoints the contract does not describe yet.
import createClient from 'openapi-fetch'
import { demoHeaders, withDemoDate } from './mode'
import { problemFromBody, readProblem } from './problem'
import type { paths } from './schema'

export const client = createClient<paths>({
  baseUrl: window.location.origin,
  // Resolved per call so MSW (which patches fetch after import) sees the requests.
  fetch: (request) => globalThis.fetch(request),
})

client.use({
  async onRequest({ request }) {
    const url = withDemoDate(new URL(request.url))
    // Rebuild explicitly: `new Request(url, request)` drops the method and body of a POST.
    const hasBody = request.method !== 'GET' && request.method !== 'HEAD'
    const forwarded = new Request(url, {
      method: request.method,
      headers: new Headers(request.headers),
      body: hasBody ? await request.clone().arrayBuffer() : undefined,
      signal: request.signal,
    })
    for (const [name, value] of Object.entries(demoHeaders())) forwarded.headers.set(name, value)
    return forwarded
  },
  // problem+json (or any non-2xx) becomes a typed `ApiProblem` for TanStack Query and the error states.
  async onResponse({ response }) {
    if (!response.ok) throw await readProblem(response)
  },
})

/** Unwraps an openapi-fetch result: the data, or a thrown `ApiProblem` (non-2xx never reaches here, see above). */
export function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.data !== undefined) return r.data
  throw problemFromBody(r.response.status, r.error)
}
