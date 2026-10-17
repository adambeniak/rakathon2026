import { demoHeaders, withDemoDate } from './mode'
import { readProblem } from './problem'

// Legacy name of `ApiProblem`: one class, so `instanceof ApiError` works for both clients.
export { ApiProblem as ApiError } from './problem'

// Temporary client for the endpoints that are not in contracts/openapi.json yet. Same role mapping and demo-date
// rule as ./client.ts. Remaining callers, to be moved to the generated client by their wiring issue; the last one
// deletes this file:
//   TODO(#31) features/referral/api.ts
//   TODO(#33) features/handover/api.ts
//   TODO(#40) features/mdt/api.ts
//   TODO(#42) features/gp/api.ts
//   TODO(#47) features/reviewer/api.ts (no wiring issue of its own; FE-24/25 batch)
//   TODO(#34) features/coordination/api.ts
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = withDemoDate(new URL(path, window.location.origin))
  const res = await fetch(url, {
    method,
    headers: {
      ...demoHeaders(),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw await readProblem(res)
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
}
