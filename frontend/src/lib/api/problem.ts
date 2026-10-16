const FALLBACK_TITLE = 'Požadavek se nezdařil'

/** RFC 7807 problem+json as the API returns it; also thrown for a response that fails its zod schema. */
export class ApiProblem extends Error {
  constructor(
    readonly status: number,
    readonly title: string,
    readonly detail?: string,
  ) {
    super(title)
    this.name = 'ApiProblem'
  }
}

/** Builds the problem from a parsed error body; anything that is not problem+json falls back to a neutral title. */
export function problemFromBody(status: number, body: unknown): ApiProblem {
  const o =
    typeof body === 'object' && body !== null ? (body as { title?: unknown; detail?: unknown }) : {}
  const title = typeof o.title === 'string' && o.title ? o.title : FALLBACK_TITLE
  return new ApiProblem(status, title, typeof o.detail === 'string' ? o.detail : undefined)
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
