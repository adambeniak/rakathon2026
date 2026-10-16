import { HttpResponse } from 'msw'

export const DEFAULT_TODAY = '2026-10-16'

export function todayOf(request: Request): string {
  return new URL(request.url).searchParams.get('today') ?? DEFAULT_TODAY
}

export function problem(status: number, title: string): Response {
  return HttpResponse.json({ type: 'about:blank', title, status }, { status, headers: { 'Content-Type': 'application/problem+json' } })
}
