import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/http'
import type { Koc, ParsedReferral } from './types'

export const useKocDirectory = () => useQuery({ queryKey: ['koc'], queryFn: () => api.get<Koc[]>('/api/koc') })

export const useParseReferral = () =>
  useMutation({ mutationFn: (filename: string) => api.post<ParsedReferral>('/api/referrals/parse', { filename }) })

export function useSubmitReferral() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { kocId: string; consent: boolean; filename: string }) =>
      api.post<{ caseId: string; state: string }>('/api/referrals', body),
    onSuccess: () => qc.invalidateQueries(),
  })
}
