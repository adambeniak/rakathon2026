import { useQuery } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { queryKey, useApiMutation, useApiQuery } from '@/lib/api/query'
import type { components } from '@/lib/api/schema'
import { adaptCase, adaptDetail } from './adapter'
import {
  caseAuditTrail,
  caseMessages,
  caseSummary,
  caseTimeline,
  documentRequests,
  documentRequestsCreated,
  proposals,
} from './schemas'

// Task hooks live in features/coordination/api.ts, document hooks in features/documents/api.ts.

export function useInbox() {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['cases', today],
    queryFn: async () => unwrap(await client.GET('/api/cases')).map(adaptCase),
  })
}

export function useCase(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'detail', today],
    queryFn: async () =>
      adaptDetail(
        unwrap(await client.GET('/api/cases/{case_id}', { params: { path: { case_id: id } } })),
      ),
  })
}

/** Documents, case events, requests, steps, MDT and feedback, oldest first; the as-of flag comes from the API. */
export function useTimeline(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'timeline', today),
    schema: caseTimeline,
    fetch: async () =>
      unwrap(
        await client.GET('/api/cases/{case_id}/timeline', { params: { path: { case_id: id } } }),
      ),
  })
}

/** Report requests to workplaces and the feedback e-mail to the GP (with the relay receipt), oldest first. */
export function useMessages(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'messages', today),
    schema: caseMessages,
    fetch: async () =>
      unwrap(
        await client.GET('/api/cases/{case_id}/messages', { params: { path: { case_id: id } } }),
      ),
  })
}

/** Audit trail of the case, newest first; the first `AUDIT_PAGE` records (`truncated` says more exist). */
export const AUDIT_PAGE = 100

export function useAudit(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'audit', today),
    schema: caseAuditTrail,
    fetch: async () =>
      unwrap(
        await client.GET('/api/cases/{case_id}/audit', {
          params: { path: { case_id: id }, query: { limit: AUDIT_PAGE } },
        }),
      ),
  })
}

/** Převzít: the coordinator accepts the referral (`odeslano` → `triage`); a refusal carries the problem title. */
export function useClaimCase() {
  return useApiMutation({
    mutate: async (id: string) =>
      unwrap(
        await client.POST('/api/cases/{case_id}/transitions', {
          params: { path: { case_id: id } },
          body: { event: 'accept' },
        }),
      ),
    schema: caseSummary,
  })
}

/** Reports the referral letter lists, quoted from it with their evidence (triage, demo step 2). */
export function useProposals(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'proposals', today),
    schema: proposals,
    fetch: async () =>
      unwrap(
        await client.GET('/api/cases/{case_id}/document-requests/proposals', {
          params: { path: { case_id: id } },
        }),
      ),
  })
}

/** Requests already sent for the case; a proposal with the same label counts as requested. */
export function useDocumentRequests(id: string) {
  const { today } = useDemo()
  return useApiQuery({
    key: queryKey('cases', id, 'document-requests', today),
    schema: documentRequests,
    fetch: async () =>
      unwrap(
        await client.GET('/api/cases/{case_id}/document-requests', {
          params: { path: { case_id: id } },
        }),
      ),
  })
}

export type DocumentRequestItem = components['schemas']['DocumentRequestItem']

/** One click: every selected proposal becomes a request; in `triage` the case moves to `ceka_na_podklady`. */
export function useRequestDocuments(id: string) {
  return useApiMutation({
    mutate: async (items: DocumentRequestItem[]) =>
      unwrap(
        await client.POST('/api/cases/{case_id}/document-requests', {
          params: { path: { case_id: id } },
          body: { items },
        }),
      ),
    schema: documentRequestsCreated,
  })
}
