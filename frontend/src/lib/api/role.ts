import type { Role } from '@/lib/domain'

/** Value of the backend `Role` enum (backend/app/domain/common.py) that `X-Demo-Role` accepts. */
export type ApiRole = 'gp' | 'coordinator' | 'koc_physician' | 'reviewer'

/** The one mapping from the UI role to the role the backend validates; every HTTP client must use it. */
export function toApiRole(role: Role): ApiRole {
  return role === 'physician' ? 'koc_physician' : role
}
