import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { api } from '@/lib/api/http'
import { adaptCase, adaptDetail } from './adapter'
import type { AuditEntry, DocumentRequest, Finding, Message, TimelineEvent } from '@/lib/domain'

// The `api` (lib/api/http.ts) calls below are not in contracts/openapi.json yet.
// TODO(#31) case reads (findings, timeline, messages, audit), claim and document requests -> generated client
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

export function useClaimCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/cases/${id}/claim`),
    onSuccess: () => qc.invalidateQueries(),
  })
}

// --- Not in contracts/openapi.json yet (F2-x): provisional paths, replace with the generated client when they land.

export const useDocumentRequests = (id: string) => useCaseQuery<DocumentRequest[]>(id, 'document-requests')

export function useRequestDocuments(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => api.post(`/api/cases/${id}/document-requests`, { ids }),
    onSuccess: () => qc.invalidateQueries(),
  })
}
