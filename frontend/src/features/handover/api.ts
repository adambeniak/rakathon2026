import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { api } from '@/lib/api/http'
import type { HandoverSection } from '@/lib/domain'
import { adaptHandover } from './adapter'
import type { HandoverView } from './types'

export function useHandover(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'handover', today],
    queryFn: async () => adaptHandover(unwrap(await client.GET('/api/cases/{case_id}/handover', { params: { path: { case_id: id } } }))),
  })
}

/** Confirmation is the only optimistic write: the pill flips at once and rolls back if the server refuses. */
export function useConfirmSection(id: string) {
  const qc = useQueryClient()
  const { today } = useDemo()
  const key = ['case', id, 'handover', today]
  return useMutation({
    // The contract confirms by section number and needs the hash of the value the physician saw (409 if it changed since).
    mutationFn: async (section: HandoverSection) =>
      unwrap(
        await client.POST('/api/cases/{case_id}/handover/sections/{number}/confirm', {
          params: { path: { case_id: id, number: section.number } },
          body: { expected_value_hash: section.valueHash ?? '', accept_missing: false },
        }),
      ),
    onMutate: async (section: HandoverSection) => {
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<HandoverView>(key)
      if (previous) {
        qc.setQueryData<HandoverView>(key, {
          ...previous,
          sections: previous.sections.map((s) => (s.key === section.key ? { ...s, confirmed: true } : s)),
        })
      }
      return { previous }
    },
    onError: (_e, _k, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}

export function useConfirmAll(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post(`/api/cases/${id}/handover/confirm-all`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}

/** Inline edit of a section: new row values plus the reason the clinician gives (recorded as Provenance). */
export function useEditSection(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { sectionKey: string; rows: Record<number, string>; reason: string }) =>
      api.post(`/api/cases/${id}/handover/sections/${v.sectionKey}/edit`, { rows: v.rows, reason: v.reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}
