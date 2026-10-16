import type { RequestHandler } from 'msw'

// Auto-collect handlers per feature: src/mocks/handlers/<feature>.ts exports `handlers` (cases, handover, mdt,
// portals, coordination, ...). A new file needs one edit of this file to bust Vite's glob cache.
const modules = import.meta.glob<{ handlers: RequestHandler[] }>('./handlers/*.ts', { eager: true })

export const handlers: RequestHandler[] = Object.values(modules).flatMap((m) => m.handlers ?? [])
