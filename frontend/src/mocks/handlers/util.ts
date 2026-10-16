import { HttpResponse } from 'msw'
import type { Role } from '@/lib/domain'

export const DEFAULT_TODAY = '2026-10-16'

export function todayOf(request: Request): string {
  return new URL(request.url).searchParams.get('today') ?? DEFAULT_TODAY
}

export function roleOf(request: Request): Role | null {
  // The generated client sends the backend's role code (`koc_physician`); the legacy client sends `physician`.
  const r = request.headers.get('x-demo-role') === 'koc_physician' ? 'physician' : request.headers.get('x-demo-role')
  return r === 'gp' || r === 'coordinator' || r === 'physician' || r === 'reviewer' ? r : null
}

export function problem(status: number, title: string): Response {
  return HttpResponse.json({ type: 'about:blank', title, status }, { status, headers: { 'Content-Type': 'application/problem+json' } })
}
