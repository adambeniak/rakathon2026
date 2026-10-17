import { useQuery } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { api } from '@/lib/api/http'
import { queryKey, useApiMutation, useApiQuery } from '@/lib/api/query'
import type { components } from '@/lib/api/schema'
import { adaptCase, adaptDetail } from './adapter'
import { caseSummary, documentRequests, documentRequestsCreated, proposals } from './schemas'
import type { AuditEntry, Finding, Message, TimelineEvent } from '@/lib/domain'

// The `api` (lib/api/http.ts) calls below are not in contracts/openapi.json.
// TODO(#33) findings -> the handover; Overview no longer reads them, the Handover screen still does
// TODO(#47) timeline, messages and audit have no contract endpoint yet
// Task hooks live in features/coordination/api.ts, document hooks in features/documents/api.ts.
function useCaseQuery<T>(id: string, part: string) {
  const { today } = useDemo()
  return useQuery({ queryKey: ['case', id, part, today], queryFn: () => api.get<T>(`/api/cases/${id}/${part}`) })
}

export function useInbox() {
  const { today } = useDemo()
  return useQuery({ queryKey: ['cases', today], queryFn: async () => unwrap(await client.GET('/api/cases')).map(adaptCase) })
}

export function useCase(id: string) {
  const { today } = useDemo()
  return useQuery({ queryKey: ['case', id, 'detail', today], queryFn: async () => adaptDetail(unwrap(await client.GET('/api/cases/{case_id}', { params: { path: { case_id: id } } }))),
  })
}

export const useFindings = (id: string) => useCaseQuery<Finding[]>(id, 'findings')
export const useTimeline = (id: string) => useCaseQuery<TimelineEvent[]>(id, 'timeline')
export const useMessages = (id: string) => useCaseQuery<Message[]>(id, 'messages')
export const useAudit = (id: string) => useCaseQuery<AuditEntry[]>(id, 'audit')

/** Převzít: the coordinator accepts the referral (`odeslano` → `triage`); a refusal carries the problem title. */
export function useClaimCase() {
  return useApiMutation({
    mutate: async (id: string) =>
      unwrap(await client.POST('/api/cases/{case_id}/transitions', { params: { path: { case_id: id } }, body: { event: 'accept' } })),
    schema: caseSummary,
  })
}

/** Reports the referral letter lists, quoted from it with their evidence (triage, demo step 2). */
export function useProposals(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'proposals', today),
    schema: proposals,
    fetch: async () => unwrap(await client.GET('/api/cases/{case_id}/document-requests/proposals', { params: { path: { case_id: id } } })),
  })
}

/** Requests already sent for the case; a proposal with the same label counts as requested. */
export function useDocumentRequests(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'document-requests', today),
    schema: documentRequests,
    fetch: async () => unwrap(await client.GET('/api/cases/{case_id}/document-requests', { params: { path: { case_id: id } } })),
  })
}

export type DocumentRequestItem = components['schemas']['DocumentRequestItem']

/** One click: every selected proposal becomes a request; in `triage` the case moves to `ceka_na_podklady`. */
export function useRequestDocuments(id: string) {
  return useApiMutation({
    mutate: async (items: DocumentRequestItem[]) =>
      unwrap(await client.POST('/api/cases/{case_id}/document-requests', { params: { path: { case_id: id } }, body: { items } })),
    schema: documentRequestsCreated,
  })
}
