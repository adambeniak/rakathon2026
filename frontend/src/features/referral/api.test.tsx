import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'
import { setDemo } from '@/lib/demo'
import { server } from '@/mocks/server'
import { multipart, usePrefillReferral, useSubmitReferral } from './api'
import { buildSubmission } from './submission'
import type { ReferralPrefill } from './types'

const LETTER = '07_PL_zadost_KOC2_2026-10-02.docx'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('referral multipart upload', () => {
  beforeEach(() => setDemo({ role: 'gp', today: '2026-10-02' }))

  it('builds the multipart body with the letter under its original file name', async () => {
    const form = multipart([
      ['letter', new File(['Pacientka: Alena Procházková'], LETTER)],
      ['payload', '{}'],
    ])
    const letter = form.get('letter') as File
    expect(letter.name).toBe(LETTER) // the backend takes the document id (and the LLM cache key) from this name
    expect(await letter.text()).toBe('Pacientka: Alena Procházková')
    expect(form.get('payload')).toBe('{}')
  })

  it('posts multipart/form-data with the letter part (the file name is native-browser only: jsdom drops it)', async () => {
    const seen: { type: string | null; letter: boolean }[] = []
    server.use(
      http.post('/api/referrals/prefill', async ({ request }) => {
        seen.push({ type: request.headers.get('content-type'), letter: (await request.clone().formData()).has('letter') })
        return HttpResponse.json({}, { status: 500 })
      }),
    )
    const { result } = renderHook(() => usePrefillReferral(), { wrapper: wrapper() })
    result.current.mutate(new File(['x'], LETTER))
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(seen).toEqual([{ type: expect.stringMatching(/^multipart\/form-data; boundary=/), letter: true }])
  })

  it('prefills from the mock with quotes of report 07 only, and submits letter + payload', async () => {
    const wrap = wrapper()
    const prefill = renderHook(() => usePrefillReferral(), { wrapper: wrap })
    const letter = new File(['x'], LETTER)
    prefill.result.current.mutate(letter)
    await waitFor(() => expect(prefill.result.current.isSuccess).toBe(true))
    const draft: ReferralPrefill = prefill.result.current.data!
    expect(draft.doc_id).toBe('07_PL_zadost_KOC2_2026-10-02')
    expect(draft.contact_person.value).toMatchObject({ relation: 'dcera' })
    const docs = new Set([draft.given, draft.birth_number, draft.insurer_code, draft.suspected_diagnosis, draft.contact_person].flatMap((f) => f.evidence?.map((e) => e.doc_id) ?? []))
    expect([...docs]).toEqual(['07_PL_zadost_KOC2_2026-10-02'])

    const submission = buildSubmission(draft, { kocId: 'koc2-nemocnice-lipova', consent: true, priority: 'urgent', note: '' })
    expect(submission).toMatchObject({ family: 'Procházková', insurer_code: '211', diagnosis_code: 'C25.0', koc_id: 'koc2-nemocnice-lipova' })

    const submit = renderHook(() => useSubmitReferral(), { wrapper: wrap })
    submit.result.current.mutate({ letter, submission: submission! })
    await waitFor(() => expect(submit.result.current.isSuccess).toBe(true))
    expect(submit.result.current.data?.case).toMatchObject({ state: 'odeslano', baton_holder: { display: 'Koordinátor KOC 2' } })
  })

  it('does not preselect urgent, and refuses a submission, when the letter states nothing', () => {
    const none = { value: null, status: 'missing' as const, derived: false, evidence: [] }
    const empty = { doc_id: 'x', given: none, family: none, sex: none, birth_date: none, age_text: none, birth_number: none, address: none, patient_phone: none, insurer_code: none, contact_person: none, requesting_gp: none, suspected_diagnosis: none, consent_statements: [], urgency_statement: none } as ReferralPrefill
    expect(buildSubmission(empty, { kocId: 'k', consent: true, priority: 'routine', note: '' })).toBeNull()
  })
})
