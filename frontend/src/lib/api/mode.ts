import { getDemo } from '@/lib/demo'
import { toApiRole } from './role'

/** True when MSW answers the requests (offline mode `VITE_MOCKS=1`, or vitest); false when the real backend does. */
export function isMocked(): boolean {
  return import.meta.env.VITE_MOCKS === '1' || import.meta.env.MODE === 'test'
}

/** Headers every request carries: who acts (the backend maps the role to a seeded person). */
export function demoHeaders(): Record<string, string> {
  return { 'X-Demo-Role': toApiRole(getDemo().role) }
}

/** The demo date is a query parameter only the MSW mocks read; the real backend has its own clock and never gets it. */
export function withDemoDate(url: URL): URL {
  if (isMocked() && !url.searchParams.has('today')) url.searchParams.set('today', getDemo().today)
  return url
}
