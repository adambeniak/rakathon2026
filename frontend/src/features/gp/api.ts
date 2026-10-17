// GP portal (demo step 6) on the generated client: the case list, the signed MDT conclusion and the read receipt.
import { useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { useDemo } from '@/app/DemoContext'
import { adaptCase } from '@/features/cases/adapter'
import { caseSummary } from '@/features/cases/schemas'
import { client, unwrap } from '@/lib/api/client'
import { queryKey, useApiMutation, useApiQuery } from '@/lib/api/query'
import type { components } from '@/lib/api/schema'

// TODO(#16) GET /api/cases is not filtered by participant yet: until it is, a GP sees every case the backend lists.
export function useGpCases() {
  const { today } = useDemo()
  return useQuery({
    queryKey: queryKey('gp', 'cases', today),
    queryFn: async () => unwrap(await client.GET('/api/cases')).map(adaptCase),
  })
}

export const mdtConclusion = z.object({
  text: z.string(),
  signed_by: z.object({ id: z.string(), display: z.string() }),
  signed_at: z.string(),
}) satisfies z.ZodType<components['schemas']['MdtConclusionOut']>

/** The conclusion as the KOC physician signed it. The backend serves it to the GP only once the feedback was sent. */
export function useMdtConclusion(caseId: string, enabled: boolean) {
  return useApiQuery({
    key: queryKey('gp', 'mdt-conclusion', caseId),
    schema: mdtConclusion,
    enabled,
    fetch: async () =>
      unwrap(
        await client.GET('/api/cases/{case_id}/mdt-conclusion', {
          params: { path: { case_id: caseId } },
        }),
      ),
  })
}

/** The GP opened the conclusion: an audited read receipt. It changes no state (`close` stays with the coordinator). */
export function useGpOpened() {
  return useApiMutation({
    mutate: async (caseId: string) =>
      unwrap(
        await client.POST('/api/cases/{case_id}/transitions', {
          params: { path: { case_id: caseId } },
          body: { event: 'gp_opened' },
        }),
      ),
    schema: caseSummary,
    invalidate: [queryKey('gp', 'cases')],
  })
}
