import { cleanup, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { vi } from 'vitest'
import { ALENA_ID } from '@/mocks/fixtures/cases'
import { AS_OF_DEFAULT } from '@/mocks/fixtures/documents'
import { buildSections } from '@/mocks/fixtures/handover'
import { toWire } from '@/mocks/fixtures/handoverWire'
import { server } from '@/mocks/server'
import { store } from '@/mocks/fixtures/store'
import { renderRoute } from '@/test/render'
import { confirmBody } from './api'
import type { SectionView } from './types'

const HANDOVER = `/cases/${ALENA_ID}/handover`
const physician = { role: 'physician', today: '2026-10-21' } as const

describe('handover step 3', () => {
  it('shows an evidence chip on every value that has evidence, not only in the section footer', async () => {
    renderRoute(HANDOVER, physician)
    const labs = await screen.findByRole('region', { name: /Laboratoř/ })
    const rows = within(labs).getAllByRole('definition')
    expect(rows.length).toBeGreaterThan(1)
    for (const row of rows) expect(within(row).getAllByRole('button', { name: /^Zdroj:/ }).length).toBeGreaterThan(0)
  })

  it('lists each missing item with its reason and the owner role, in Czech', async () => {
    renderRoute(HANDOVER, physician)
    const ecog = await screen.findByRole('region', { name: /Stav výkonnosti/ })
    expect(within(ecog).getByText('Stav výkonnosti (ECOG)')).toBeInTheDocument()
    expect(within(ecog).getByText(/v dokumentaci neuvedeno · Může doplnit: ošetřující lékař KOC/)).toBeInTheDocument()
    const contacts = screen.getByRole('region', { name: /Kontakty/ })
    expect(within(contacts).getByText(/Může doplnit: koordinátor KOC/)).toBeInTheDocument()
  })

  it('shows the findings of a conflicting section with the wording of the API', async () => {
    renderRoute(HANDOVER, physician)
    const meds = await screen.findByRole('region', { name: /Léková anamnéza/ })
    expect(within(meds).getByRole('list', { name: 'Související zjištění' })).toHaveTextContent(/Nesoulad mezi datem výkonu/)
  })

  it('"Ponechat jako chybějící" sends accept_missing:true with the section hash; a section that is not missing sends false', async () => {
    const bodies: Array<{ number: string; body: Record<string, unknown> }> = []
    server.use(
      http.post('/api/cases/:id/handover/sections/:number/confirm', async ({ params, request }) => {
        bodies.push({ number: String(params.number), body: (await request.json()) as Record<string, unknown> })
        return HttpResponse.json(toWire(ALENA_ID, AS_OF_DEFAULT, buildSections({}, AS_OF_DEFAULT), {}))
      }),
    )
    renderRoute(HANDOVER, physician)
    await userEvent.click(await screen.findByRole('button', { name: 'Ponechat údaj v sekci Stav výkonnosti jako chybějící' }))
    await userEvent.click(screen.getByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    await vi.waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[0]).toEqual({ number: '9', body: { expected_value_hash: expect.stringMatching(/^[0-9a-f]{64}$/), accept_missing: true } })
    expect(bodies[1]).toEqual({ number: '8', body: { expected_value_hash: expect.stringMatching(/^[0-9a-f]{64}$/), accept_missing: false } })
  })

  it('an edit sends edited_value in the confirm request; there is no confirm-all request', () => {
    const section = { valueHash: 'a'.repeat(64) } as SectionView
    expect(confirmBody({ kind: 'edit', section, text: 'Bez alergií' })).toEqual({
      expected_value_hash: 'a'.repeat(64),
      accept_missing: false,
      edited_value: 'Bez alergií',
    })
    expect(confirmBody({ kind: 'confirm', section })).not.toHaveProperty('edited_value')
  })

  it('copy of an unconfirmed section is prefixed "Návrh AI – čeká na potvrzení"; a confirmed one is not', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    renderRoute(HANDOVER, physician)
    await userEvent.click(await screen.findByRole('button', { name: 'Kopírovat sekci: Alergie' }))
    expect(writeText).toHaveBeenLastCalledWith(expect.stringMatching(/^Návrh AI – čeká na potvrzení\n8\. Alergie/))
    await userEvent.click(screen.getByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    await within(screen.getByRole('region', { name: /Alergie/ })).findByText('Potvrdil(a) MUDr. Havelka')
    await userEvent.click(screen.getByRole('button', { name: 'Kopírovat sekci: Alergie' }))
    // A confirmed copy says it was assembled with AI, by whom it was confirmed, and which documents it cites.
    expect(writeText).toHaveBeenLastCalledWith(
      expect.stringMatching(/^Sestaveno s pomocí AI z dokumentace, potvrdil\(a\) MUDr\. Havelka\n8\. Alergie[\s\S]*\nZdroje: 07_PL_zadost_KOC2_2026-10-02$/),
    )
  })

  it('an edited value is shown without a source citation and the old sources are labelled as the AI draft\'s', async () => {
    renderRoute(HANDOVER, physician)
    await userEvent.click(await screen.findByRole('button', { name: 'Upravit sekci: Alergie' }))
    const section = screen.getByRole('region', { name: /Alergie/ })
    const input = within(section).getByRole('textbox', { name: /^Hodnota:/ })
    expect(input).toHaveFocus()
    await userEvent.clear(input)
    await userEvent.type(input, 'Bez známých alergií')
    await userEvent.click(within(section).getByRole('button', { name: 'Uložit a potvrdit' }))
    await within(section).findByText('bez citace zdroje')
    expect(within(section).getByText('Zdroje původního návrhu AI (hodnota je upravena lékařem):')).toBeInTheDocument()
    expect(within(section).queryByText('Zdroje oddílu:')).toBeNull()
    const row = within(section).getByText('Bez známých alergií').closest('dd')!
    expect(within(row).queryByRole('button', { name: /^Zdroj:/ })).toBeNull() // no chip on the physician's own value
    expect(screen.getByRole('heading', { name: /Alergie/ })).toHaveFocus() // focus returns after the form closes
  })

  it('a finding shows the Nesouhlasí pill and the cited documents', async () => {
    renderRoute(HANDOVER, physician)
    const meds = await screen.findByRole('region', { name: /Léková anamnéza/ })
    const finding = within(within(meds).getByRole('list', { name: 'Související zjištění' })).getAllByRole('listitem')[0]!
    expect(within(finding).getByText('Nesouhlasí')).toBeInTheDocument()
    expect(within(finding).getAllByRole('button', { name: /^Zdroj:/ }).length).toBeGreaterThan(0)
  })

  it('nothing is shown as confirmed before the server has answered', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    server.use(
      http.post('/api/cases/:id/handover/sections/:number/confirm', async () => {
        await gate
        store.confirmed['8_allergies'] = 'MUDr. Havelka' // what the real mock route would record
        return HttpResponse.json(toWire(ALENA_ID, AS_OF_DEFAULT, buildSections(store.confirmed, AS_OF_DEFAULT), {}))
      }),
    )
    renderRoute(HANDOVER, physician)
    await userEvent.click(await screen.findByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    const section = screen.getByRole('region', { name: /Alergie/ })
    expect(await within(section).findByText('Ukládám potvrzení…')).toBeInTheDocument()
    expect(within(section).queryByText('Potvrzeno lékařem')).toBeNull()
    release()
    await within(section).findByText('Potvrzeno lékařem')
  })

  it('shows the problem title when the server refuses a confirmation', async () => {
    server.use(
      http.post('/api/cases/:id/handover/sections/:number/confirm', () =>
        HttpResponse.json({ title: 'Hodnota sekce se mezitím změnila', status: 409 }, { status: 409, headers: { 'Content-Type': 'application/problem+json' } }),
      ),
    )
    renderRoute(HANDOVER, physician)
    await userEvent.click(await screen.findByRole('button', { name: 'Potvrdit sekci: Alergie' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Akce se nezdařila: Hodnota sekce se mezitím změnila')
    expect(screen.queryByText('Potvrdil(a) MUDr. Havelka')).toBeNull() // rolled back
  })

  describe('a section whose open question the physician answered with a value of their own', () => {
    const by = { display: 'MUDr. Havelka', id: 'havelka', role: 'koc_physician' }
    const withQuestion = (review: unknown) => {
      const base = toWire(ALENA_ID, AS_OF_DEFAULT, buildSections({}, AS_OF_DEFAULT), {})
      return {
        ...base,
        fields: {
          ...base.fields,
          '5_mdt_question': {
            status: 'needs_clarification',
            value: 'Posouzení resekability.',
            items: [{ label: 'Upraveno lékařem', value: 'Posouzení resekability.', evidence: [] }],
            evidence: [],
            missing: ['explicit_mdt_question'],
            missing_items: [{ item: 'explicit_mdt_question', reason: 'v žádosti chybí konkrétní otázka pro MDT', suggested_owner: 'gp' }],
            review,
            value_hash: 'b'.repeat(64),
          },
        },
      }
    }
    const open = async (review: unknown) => {
      server.use(http.get('/api/cases/:id/handover', () => HttpResponse.json(withQuestion(review))))
      renderRoute(HANDOVER, physician)
      return screen.findByRole('region', { name: /Otázka pro MDT/ })
    }

    it('shows the gap as "Doplněno lékařem" and drops the "K upřesnění" badge after the edit is confirmed', async () => {
      const section = await open({ state: 'confirmed', by, edited: true })
      expect(within(section).getByText('Doplněno lékařem')).toBeInTheDocument()
      expect(within(section).getByText('Výslovná otázka pro MDT')).toHaveClass('line-through')
      expect(within(section).queryByText('K upřesnění')).toBeNull()
      expect(within(section).queryByText('Chybí', { selector: 'span' })).toBeNull()
      expect(within(section).queryByText('explicit_mdt_question')).toBeNull() // never the raw key
    })

    it('keeps the badge and the open gap with its reason while the section is not confirmed with an edit', async () => {
      for (const review of [null, { state: 'confirmed', by, edited: false }]) {
        const section = await open(review)
        expect(within(section).getByText('K upřesnění')).toBeInTheDocument()
        expect(within(section).getByText(/v žádosti chybí konkrétní otázka pro MDT/)).toBeInTheDocument()
        expect(within(section).queryByText('Doplněno lékařem')).toBeNull()
        cleanup()
      }
    })
  })
})
