// Mock endpoints of the documents feature (upload, per-document status). The list itself is part of `GET /api/cases/:id`
// (handlers/cases.ts). Empty on purpose: the step 3 wiring issue adds its handlers here and edits no other mock file.
import type { RequestHandler } from 'msw'

export const handlers: RequestHandler[] = []
