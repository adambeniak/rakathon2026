import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { adaptHandover } from './adapter'
import type { SectionView } from './types'

export function useHandover(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'handover', today],
    queryFn: async () => adaptHandover(unwrap(await client.GET('/api/cases/{case_id}/handover', { params: { path: { case_id: id } } }))),
  })
}

/** What the physician does with one section. Everything goes through `confirm`; there is no bulk confirmation. */
export type SectionReview =
  | { kind: 'confirm'; section: SectionView }
  | { kind: 'accept_missing'; section: SectionView }
  /** Saves the physician's own value and confirms it in the same call (`edited_value`). */
  | { kind: 'edit'; section: SectionView; text: string }

/** Request body of `POST …/sections/{number}/confirm`; `accept_missing` is only valid for a section that is missing. */
export function confirmBody(r: SectionReview) {
  return {
    expected_value_hash: r.section.valueHash ?? '',
    accept_missing: r.kind === 'accept_missing',
    ...(r.kind === 'edit' ? { edited_value: r.text } : {}),
  }
}

/** Nothing is shown as confirmed before the server has recorded it (Provenance): the card shows "saving" meanwhile. */
export function useReviewSection(id: string) {
  const qc = useQueryClient()
  return useMutation({
    // The contract confirms by section number and needs the hash of the value the physician saw (409 if it changed since).
    mutationFn: async (r: SectionReview) =>
      unwrap(
        await client.POST('/api/cases/{case_id}/handover/sections/{number}/confirm', {
          params: { path: { case_id: id, number: r.section.number } },
          body: confirmBody(r),
        }),
      ),
    onSettled: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}
