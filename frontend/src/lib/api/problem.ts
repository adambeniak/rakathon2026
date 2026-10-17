import { z } from 'zod'

const FALLBACK_TITLE = 'Požadavek se nezdařil'

/**
 * RFC 7807 problem+json as the API returns it; also thrown for a response that fails its zod schema. `title` and
 * `detail` are Czech texts for people; programs branch on `status`, `code` and `blockingItems`, never on the wording.
 */
export class ApiProblem extends Error {
  constructor(
    readonly status: number,
    readonly title: string,
    readonly detail?: string,
    /** Refused transition: `invalid_transition | guard_failed | case_postponed` (409) or `forbidden_role` (403). */
    readonly code?: string,
    /** Readiness item keys a `guard_failed` of `mark_ready_mdt` blocks on (`blocking_items`). */
    readonly blockingItems?: string[],
  ) {
    super(title)
    this.name = 'ApiProblem'
  }
}

// Each field on its own: a malformed field is dropped, the rest of the problem is kept.
const problemBody = z.object({
  title: z.string().min(1).optional().catch(undefined),
  detail: z.string().optional().catch(undefined),
  code: z.string().min(1).optional().catch(undefined),
  blocking_items: z.array(z.string()).optional().catch(undefined),
})

/** Builds the problem from a parsed error body; anything that is not problem+json falls back to a neutral title. */
export function problemFromBody(status: number, body: unknown): ApiProblem {
  const parsed = problemBody.safeParse(body)
  const o = parsed.success ? parsed.data : {}
  return new ApiProblem(status, o.title ?? FALLBACK_TITLE, o.detail, o.code, o.blocking_items)
}

export async function readProblem(response: Response): Promise<ApiProblem> {
  let body: unknown
  try {
    body = await response.clone().json()
  } catch {
    /* not JSON */
  }
  return problemFromBody(response.status, body)
}

/** Text for an error state: the problem title the API sent, never a raw exception message. */
export function problemTitle(error: unknown): string {
  return error instanceof ApiProblem ? error.title : FALLBACK_TITLE
}
