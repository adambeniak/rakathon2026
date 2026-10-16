import type { RequestHandler } from 'msw'

// Auto-collect handlers per feature: src/mocks/handlers/<feature>.ts exports `handlers`.
const modules = import.meta.glob<{ handlers: RequestHandler[] }>('./handlers/*.ts', { eager: true })

export const handlers: RequestHandler[] = Object.values(modules).flatMap((m) => m.handlers ?? [])
