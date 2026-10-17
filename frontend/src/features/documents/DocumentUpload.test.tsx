import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { client } from '@/lib/api/client'
import { ApiProblem } from '@/lib/api/problem'
import { ALENA_ID } from '@/mocks/fixtures/cases'
import { renderRoute } from '@/test/render'
import { uploadForm } from './api'

const DOCS = `/cases/${ALENA_ID}/documents`
const pdf = (name: string) => new File(['%PDF-1.7 test'], name, { type: 'application/pdf' })
const received = { document: { doc_id: 'x', title: 'x', authored_at: '2026-09-29', received_at: '2026-10-16T09:00:00+02:00' }, open_requests_remaining: 0, case: {} }

// jsdom's FormData cannot be sent through fetch (the request never completes), so the transport is not exercised here:
// these tests check what the screen hands to the generated client. The multipart boundary and file name surviving
// `lib/api/client.ts` (Request rebuilt from an ArrayBuffer) were checked with Node's native fetch, see the PR.
describe('document upload', () => {
  it('builds a multipart body that keeps the original file name', () => {
    const form = uploadForm(pdf('06_UZ_bricha_2026-09-29.pdf'), { authoredAt: '2026-09-29', requestId: 'req-1' })
    expect((form.get('file') as File).name).toBe('06_UZ_bricha_2026-09-29.pdf')
    expect(form.get('authored_at')).toBe('2026-09-29')
    expect(form.get('request_id')).toBe('req-1')
    expect(uploadForm(pdf('a.pdf')).has('authored_at')).toBe(false)
  })

  it('posts every chosen file to the contract path, one by one, each under its original name', async () => {
    const post = vi.spyOn(client, 'POST').mockResolvedValue({ data: received, response: new Response() } as never)
    renderRoute(DOCS, { role: 'coordinator', today: '2026-10-16' })
    await userEvent.upload(await screen.findByLabelText('Soubor zprávy'), [pdf('06_UZ_bricha_2026-09-29.pdf'), pdf('08_CT_KOC1_2026-10-08.pdf')])
    await userEvent.click(screen.getByRole('button', { name: 'Nahrát' }))
    expect(await screen.findByText('Nahráno: 08_CT_KOC1_2026-10-08.pdf')).toBeInTheDocument()
    expect(screen.getByText('Nahráno: 06_UZ_bricha_2026-09-29.pdf')).toBeInTheDocument()
    expect(post).toHaveBeenCalledTimes(2)
    const [path, init] = post.mock.calls[0] as unknown as [string, { params: unknown; bodySerializer: () => FormData }]
    expect(path).toBe('/api/cases/{case_id}/documents')
    expect(init.params).toEqual({ path: { case_id: ALENA_ID } })
    expect((init.bodySerializer().get('file') as File).name).toBe('06_UZ_bricha_2026-09-29.pdf')
    post.mockRestore()
  })

  it('shows the problem title of a refused upload next to the file name', async () => {
    const post = vi.spyOn(client, 'POST').mockRejectedValue(new ApiProblem(422, 'Podporovány jsou pouze soubory PDF a DOCX'))
    renderRoute(DOCS, { role: 'coordinator', today: '2026-10-16' })
    await userEvent.upload(await screen.findByLabelText('Soubor zprávy'), new File(['x'], 'poznamky.txt', { type: 'text/plain' }), { applyAccept: false })
    await userEvent.click(screen.getByRole('button', { name: 'Nahrát' }))
    expect(await screen.findByText('Nepodařilo se nahrát poznamky.txt: Podporovány jsou pouze soubory PDF a DOCX')).toBeInTheDocument()
    post.mockRestore()
  })

  it('only the coordinator can upload', async () => {
    renderRoute(DOCS, { role: 'physician', today: '2026-10-16' })
    expect(await screen.findByText('Zprávy k případu přidává koordinátorka KOC.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Soubor zprávy')).toBeNull()
  })
})
