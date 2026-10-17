import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '@/mocks/server'
import type { Role } from '@/lib/domain'
import { renderRoute } from '@/test/render'

// The person `X-Demo-Role` maps to in the backend (first seeded person of the role by PractitionerRole id,
// backend/app/security/actor.py), named as in its Provenance/AuditEvent. Pinned on the backend side by
// backend/tests/unit/test_demo_actor.py: change both together.
const BACKEND_PERSON: Record<Role, string> = {
  gp: 'MUDr. Tomáš Řezníček',
  coordinator: 'Bc. Lucie Dvořáková',
  physician: 'doc. MUDr. Pavel Hrubý, Ph.D.',
  reviewer: 'MUDr. Jitka Benešová',
}

describe('header', () => {
  it.each(Object.entries(BACKEND_PERSON) as Array<[Role, string]>)(
    'shows for role %s the person the backend records as the actor',
    async (role, person) => {
      renderRoute('/', { role, today: '2026-10-21' })
      const banner = await screen.findByRole('banner')
      expect(within(banner).getByText(person)).toBeInTheDocument()
    },
  )
})

describe('simulated date switcher', () => {
  // Demo step 3 runs on 20. 10.: the as-of rule drops a report authored on or after the as-of day, and report 11 is
  // authored 19. 10., so 19. 10. would hide the histology conflict (#121).
  it('offers 20. 10. 2026 as a preset, so step 3 needs no curl', async () => {
    renderRoute('/', { today: '2026-10-21' })
    const select = await screen.findByRole('combobox', { name: 'Simulované datum' })
    expect(within(select).getByRole('option', { name: '20. 10. 2026' })).toBeInTheDocument()

    await userEvent.selectOptions(select, '2026-10-20')
    expect(select).toHaveValue('2026-10-20')
    expect(within(select).queryByRole('option', { name: /Jiné datum/ })).toBeNull()
  })
})

describe('case header', () => {
  const minimal = {
    id: 'rakathon-2026-prochazkova',
    patient: {
      display_name: 'Test Pacient',
      birth_date: '1963-07-22',
      age_years: 63,
      sex: 'female',
    },
    state: 'kompletni',
    bucket: 'aktivni',
    postponed: false,
    document_count: 0,
    documents: [],
  }

  it('leaves out what the backend does not send instead of showing "RČ — · —"', async () => {
    server.use(http.get('/api/cases/:id', () => HttpResponse.json(minimal)))
    renderRoute('/cases/rakathon-2026-prochazkova', { role: 'physician', today: '2026-10-21' })

    const header = await screen.findByRole('region', { name: 'Test Pacient' })
    expect(within(header).getByText('22. 7. 1963')).toBeInTheDocument()
    expect(within(header).queryByText(/RČ/)).toBeNull()
    expect(within(header).queryByText(/Pojišťovna|Centrum|Odesílající PL/)).toBeNull()
    expect(header.textContent).not.toMatch(/·\s*—|—\s*·/)
  })

  it('shows the parties that are known, and only those', async () => {
    server.use(
      http.get('/api/cases/:id', () =>
        HttpResponse.json({
          ...minimal,
          patient: { ...minimal.patient, insurer_code: '211' },
          referring_gp: { name: 'MUDr. Tomáš Řezníček' },
        }),
      ),
    )
    renderRoute('/cases/rakathon-2026-prochazkova', { role: 'physician', today: '2026-10-21' })

    const header = await screen.findByRole('region', { name: 'Test Pacient' })
    expect(
      within(header).getByText('Pojišťovna: 211 · Odesílající PL: MUDr. Tomáš Řezníček'),
    ).toBeInTheDocument()
    expect(within(header).queryByText(/Centrum/)).toBeNull()
  })
})
