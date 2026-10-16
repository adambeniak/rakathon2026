// TanStack Query helpers for the feature `api.ts` files: every response is parsed with zod at the boundary and every
// failure is an `ApiProblem` (error UIs show `problemTitle(error)`).
//
// Query-key convention: `[feature, ...scope]`, e.g. queryKey('coordination', caseId, 'tasks'). The first element is
// the feature folder, so a feature invalidates only its own data: `invalidate: [queryKey('coordination', caseId)]`.
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { ZodError, type z } from 'zod'
import { ApiProblem } from './problem'

export const queryKey = (feature: string, ...scope: readonly (string | number)[]): QueryKey => [
  feature,
  ...scope,
]

/** Parses a response body. A mismatch becomes an `ApiProblem` whose detail lists field paths only, never values. */
async function parseBody<S extends z.ZodType>(schema: S, body: unknown): Promise<z.output<S>> {
  try {
    return await schema.parseAsync(body)
  } catch (error) {
    if (!(error instanceof ZodError)) throw error
    const detail = error.issues.map((i) => `${i.path.join('.') || '(root)'}: ${i.code}`).join('; ')
    throw new ApiProblem(502, 'Odpověď serveru má neočekávaný tvar', detail)
  }
}

export function useApiQuery<S extends z.ZodType>(opts: {
  key: QueryKey
  schema: S
  /** Returns the raw body, e.g. `unwrap(await client.GET(...))`. */
  fetch: () => Promise<unknown>
  enabled?: boolean
}) {
  return useQuery<z.output<S>, ApiProblem>({
    queryKey: opts.key,
    enabled: opts.enabled,
    queryFn: async () => parseBody(opts.schema, await opts.fetch()),
  })
}

export function useApiMutation<V, S extends z.ZodType>(opts: {
  mutate: (variables: V) => Promise<unknown>
  schema: S
  /** Keys to refetch after success; omitted = every query (the demo's state is shared across screens). */
  invalidate?: readonly QueryKey[]
}) {
  const qc = useQueryClient()
  return useMutation<z.output<S>, ApiProblem, V>({
    mutationFn: async (variables) => parseBody(opts.schema, await opts.mutate(variables)),
    onSuccess: async () => {
      if (!opts.invalidate) return qc.invalidateQueries()
      await Promise.all(opts.invalidate.map((queryKey) => qc.invalidateQueries({ queryKey })))
    },
  })
}
