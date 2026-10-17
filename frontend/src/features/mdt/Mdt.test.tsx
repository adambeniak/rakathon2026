import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import { mdtRecordFileName } from '@/features/mdt/api'
import { buildSections } from '@/mocks/fixtures/handover'
import { toWire } from '@/mocks/fixtures/handoverWire'
import { problem } from '@/mocks/handlers/util'
import { server } from '@/mocks/server'
import { renderRoute } from '@/test/render'

const ALENA_ID = 'rakathon-2026-prochazkova'
const MDT = `/cases/${ALENA_ID}/mdt`

/** URLs of the requests the screen sends (MSW lifecycle; the default handlers still answer). */
function recordUrls(): URL[] {
  const urls: URL[] = []
  server.events.on('request:start', ({ request }) => urls.push(new URL(request.url)))
  return urls
}
afterEach(() => {
  server.events.removeAllListeners()
  vi.restoreAllMocks()
})

describe('as-of', () => {
  it('shows the cut-off the API answered with and sends no as_of of its own', async () => {
    const urls = recordUrls()
    renderRoute(MDT, { role: 'physician', today: '2026-10-21' })
    expect(await screen.findByText('Stav k začátku MDT: 21. 10. 2026 8:00')).toBeInTheDocument()
    expect(screen.queryByLabelText(/as-of/i)).not.toBeInTheDocument() // no picker: the server decides
    const handover = urls.filter((u) => u.pathname.endsWith('/handover'))
    expect(handover.length).toBeGreaterThan(0)
    expect(handover.every((u) => !u.searchParams.has('as_of'))).toBe(true)
  })

  it('stores the MDT-start handover when the screen opens, so earlier decisions carry over (#122)', async () => {
    const methods: string[] = []
    server.events.on('request:start', ({ request }) => {
      if (new URL(request.url).pathname.endsWith('/handover')) methods.push(request.method)
    })
    renderRoute(MDT, { role: 'coordinator', today: '2026-10-21' })
    await screen.findByRole('region', { name: 'Stav handoveru k MDT' })
    expect(methods).toContain('POST')
    expect(methods).not.toContain('GET')
  })

  it('follows another cut-off from the API instead of a constant in the UI', async () => {
    const asOf = '2026-10-21T08:00:00+02:00'
    server.use(
      http.post('/api/cases/:id/handover', () =>
        HttpResponse.json({
          ...toWire(ALENA_ID, asOf, buildSections({}, asOf), {}, new Set()),
          as_of: '2026-10-22T09:30:00+02:00',
        }),
      ),
    )
    renderRoute(MDT, { role: 'physician', today: '2026-10-21' })
    expect(await screen.findByText('Stav k začátku MDT: 22. 10. 2026 9:30')).toBeInTheDocument()
  })
})

describe('MDT screen', () => {
  it('summarises the section statuses, lists the findings and the reports after the MDT', async () => {
    const { container } = renderRoute(MDT, { role: 'physician', today: '2026-10-21' })
    const summary = await screen.findByRole('region', { name: 'Stav handoveru k MDT' })
    expect(within(summary).getByText(/Potvrzeno lékařem: 0 z 15 sekcí/)).toBeInTheDocument()
    expect(within(summary).getByText(/Chybí:/)).toBeInTheDocument()

    const findings = screen.getByRole('region', { name: 'Nesoulady v dokumentaci' })
    expect(within(findings).getAllByRole('listitem').length).toBeGreaterThan(0)

    // Reports 12 and 13 come from the API's excluded list, with the API's reason.
    const excluded = screen.getByRole('region', { name: 'Po MDT – nezahrnuto' })
    const items = within(excluded).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('12')
    expect(items[1]).toHaveTextContent('13')
    expect(items[0]).toHaveTextContent('Dokument vznikl nebo byl přijat po termínu as-of')
    expect(await axe(container)).toHaveNoViolations()
  })

  it('shows the empty state when no handover could be assembled', async () => {
    server.use(http.post('/api/cases/:id/handover', () => problem(404, 'Případ nebyl nalezen')))
    renderRoute(MDT, { role: 'physician', today: '2026-10-21' })
    expect(await screen.findByText('MDT podklady nejsou k dispozici')).toBeInTheDocument()
  })
})

describe('record download (DOCX, PDF)', () => {
  function stubDownload() {
    const create = vi.fn(() => 'blob:mdt')
    const revoke = vi.fn()
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
    const names: string[] = []
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      names.push(this.download)
    })
    return { create, names }
  }

  it('file name is ours: case, cut-off date and NAVRH while a section is unconfirmed', () => {
    expect(mdtRecordFileName(ALENA_ID, '2026-10-21T08:00:00+02:00', true)).toBe(
      'MDT_zapis_rakathon-2026-prochazkova_2026-10-21_NAVRH.docx',
    )
    expect(mdtRecordFileName(ALENA_ID, '2026-10-21T08:00:00+02:00', false)).toBe(
      'MDT_zapis_rakathon-2026-prochazkova_2026-10-21.docx',
    )
  })

  it('fetches mdt-record as docx and saves the blob under our file name', async () => {
    const urls = recordUrls()
    const { create, names } = stubDownload()
    renderRoute(MDT, { role: 'physician', today: '2026-10-21' })
    const button = await screen.findByRole('button', { name: 'Stáhnout zápis (DOCX)' })
    await waitFor(() => expect(button).toBeEnabled())
    await userEvent.click(button)
    await waitFor(() =>
      expect(names).toEqual(['MDT_zapis_rakathon-2026-prochazkova_2026-10-21_NAVRH.docx']),
    )
    const record = urls.find((u) => u.pathname.endsWith('/mdt-record'))
    expect(record?.searchParams.get('format')).toBe('docx')
    expect(create).toHaveBeenCalledOnce()
    const blob = (create.mock.calls[0] as unknown as [Blob])[0]
    expect(blob.size).toBe(4) // the bytes the server sent
    expect(blob.type).toBe(
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
  })

  it('offers the same record as PDF: format=pdf, a .pdf file name and the PDF bytes', async () => {
    expect(mdtRecordFileName(ALENA_ID, '2026-10-21T08:00:00+02:00', true, 'pdf')).toBe(
      'MDT_zapis_rakathon-2026-prochazkova_2026-10-21_NAVRH.pdf',
    )
    const urls = recordUrls()
    const { create, names } = stubDownload()
    renderRoute(MDT, { role: 'coordinator', today: '2026-10-21' })
    const button = await screen.findByRole('button', { name: 'Stáhnout zápis (PDF)' })
    await waitFor(() => expect(button).toBeEnabled())
    await userEvent.click(button)
    await waitFor(() =>
      expect(names).toEqual(['MDT_zapis_rakathon-2026-prochazkova_2026-10-21_NAVRH.pdf']),
    )
    const record = urls.find((u) => u.pathname.endsWith('/mdt-record'))
    expect(record?.searchParams.get('format')).toBe('pdf')
    const blob = (create.mock.calls[0] as unknown as [Blob])[0]
    expect(blob.type).toBe('application/pdf')
    expect(blob.size).toBe(5)
    expect(
      screen.getByText(/Po zapsání závěru MDT obsahuje zápis v oddílu 6 jeho znění potvrzené lékařem v systému/),
    ).toBeInTheDocument()
  })

  it('shows the API problem title when the record is refused', async () => {
    stubDownload()
    server.use(
      http.get('/api/cases/:id/mdt-record', () =>
        problem(403, 'Zápis může stáhnout pouze tým KOC'),
      ),
    )
    renderRoute(MDT, { role: 'coordinator', today: '2026-10-21' })
    const button = await screen.findByRole('button', { name: 'Stáhnout zápis (DOCX)' })
    await waitFor(() => expect(button).toBeEnabled())
    await userEvent.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent('Zápis může stáhnout pouze tým KOC')
  })

  it('is not offered to the GP', async () => {
    renderRoute(MDT, { role: 'gp', today: '2026-10-21' })
    await screen.findByRole('region', { name: 'Stav handoveru k MDT' })
    expect(screen.queryByRole('button', { name: 'Stáhnout zápis (DOCX)' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Stáhnout zápis (PDF)' })).not.toBeInTheDocument()
  })
})
