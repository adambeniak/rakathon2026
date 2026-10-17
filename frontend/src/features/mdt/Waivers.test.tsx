import { render, screen } from '@testing-library/react'
import { adaptDetail } from '@/features/cases/adapter'
import { api } from '@/lib/api/http'
import { setDemo } from '@/lib/demo'
import type { components } from '@/lib/api/schema'
import { resetStore } from '@/mocks/fixtures/store'
import { Waivers } from './Waivers'

const ID = 'rakathon-2026-prochazkova'

describe('Waivers', () => {
  it('renders nothing when no item was waived', () => {
    const { container } = render(<Waivers waivers={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('labels the item in Czech, keeps an unknown key as is, and never invents a missing signer', () => {
    render(
      <Waivers
        waivers={[
          { item: 'ct_staging', reason: 'CT bude doplněno.', by: null, at: '2026-10-20T12:15:00Z' },
          { item: 'new_item', reason: 'Důvod.', by: 'MUDr. Test', at: '2026-10-20T12:15:00Z' },
        ]}
      />,
    )
    expect(screen.getByText('CT staging')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Prominuto lékařem: jméno neuvedeno, 20. 10. 2026 14:15, důvod: CT bude doplněno.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('new_item')).toBeInTheDocument()
  })
})

describe('case detail mock', () => {
  beforeEach(() => resetStore())

  it('carries readiness_waivers to the KOC team only, and gp_opened_at once the GP opened the conclusion', async () => {
    setDemo({ role: 'physician', today: '2026-10-20' })
    await api.post(`/api/cases/${ID}/transitions`, {
      event: 'mark_ready_mdt',
      waivers: [{ item: 'performance_status', reason: 'Doplní lékař.' }],
    })
    const asPhysician = adaptDetail(
      await api.get<components['schemas']['CaseDetail']>(`/api/cases/${ID}`),
    )
    expect(asPhysician.readinessWaivers).toEqual([
      expect.objectContaining({ item: 'performance_status', reason: 'Doplní lékař.' }),
    ])
    expect(asPhysician.gpOpenedAt).toBeNull()

    setDemo({ role: 'gp', today: '2026-10-20' })
    const asGp = adaptDetail(await api.get<components['schemas']['CaseDetail']>(`/api/cases/${ID}`))
    expect(asGp.readinessWaivers).toEqual([])
  })
})
