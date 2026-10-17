import { cleanup, screen } from '@testing-library/react'
import { renderRoute } from '@/test/render'
import { intervalText } from './intervals'

afterEach(cleanup)

describe('case header time-to-treatment intervals (CaseDetail.intervals)', () => {
  it('renders what the API computed: T1 not recorded, T2 running before the MDT, T3 not started', async () => {
    renderRoute('/cases/rakathon-2026-prochazkova', { today: '2026-10-21' })

    const clocks = await screen.findByRole('group', { name: 'Časové intervaly' })
    expect(clocks).toHaveTextContent('nezaznamenánoT1 · první návštěva PL → žádost do KOC')
    expect(clocks).toHaveTextContent('běžíT2 · žádost do KOC → MDT')
    expect(clocks).toHaveTextContent('zatím neběžíT3 · MDT → onkologické konzilium')
    expect(screen.getByText(/Orientační ukazatele \(proxy\)/)).toBeInTheDocument()
  })
})

describe('intervalText', () => {
  it('shows days only for a measured interval and says why otherwise', () => {
    expect(intervalText({ days: 19, status: 'measured' })).toBe('19 dní')
    expect(intervalText({ days: 1, status: 'measured' })).toBe('1 den')
    expect(intervalText({ days: 0, status: 'measured' })).toBe('0 dní')
    expect(intervalText({ days: null, status: 'running' })).toBe('běží')
    expect(intervalText({ days: null, status: 'not_started' })).toBe('zatím neběží')
    expect(intervalText({ days: null, status: 'not_recorded' })).toBe('nezaznamenáno')
    expect(intervalText({ days: null, status: 'inconsistent' })).toBe('nesoulad dat (konec před začátkem)')
    expect(intervalText(undefined)).toBe('—')
  })
})
