import { getDemo } from '@/lib/demo'

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

// The only place that calls fetch. Replace with the generated openapi-fetch client (./client.ts)
// once contracts/openapi.json exists.
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = new URL(path, window.location.origin)
  if (!url.searchParams.has('today')) url.searchParams.set('today', getDemo().today)
  const res = await fetch(url, {
    method,
    headers: { 'X-Demo-Role': getDemo().role, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    let title = 'Požadavek se nezdařil'
    try {
      title = ((await res.json()) as { title?: string }).title ?? title
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, title)
  }
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
}
