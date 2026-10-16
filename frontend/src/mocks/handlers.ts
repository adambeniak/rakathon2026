import type { RequestHandler } from 'msw'

// Auto-collect handlers per feature: src/mocks/handlers/<feature>.ts exports `handlers` (referral, cases, handover,
// documents, coordination, mdt, portals). A new file needs one edit of this file to bust Vite's glob cache.
// Test files are excluded, otherwise their tests would be registered again in every test file that loads the mocks.
const modules = import.meta.glob<{ handlers: RequestHandler[] }>(['./handlers/*.ts', '!./handlers/*.test.ts'], { eager: true })

export const handlers: RequestHandler[] = Object.values(modules).flatMap((m) => m.handlers ?? [])
