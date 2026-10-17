import { cleanup, screen, within } from '@testing-library/react'
import { client } from '@/lib/api/client'
import { setDemo } from '@/lib/demo'
import { renderRoute } from '@/test/render'
import { reviewerCase } from './api'

afterEach(cleanup)

describe('insurer reviewer screen (#105, contract GET /api/reviewer/cases)', () => {
  it('shows a minimal summary of the own insurer only: initials, birth year, MKN-10 group, T1–T3, delivery', async () => {
    renderRoute('/reviewer', { role: 'reviewer', today: '2026-10-21' })

    const table = await screen.findByRole('table', { name: 'Případy pojištěnců' })
    const alena = within(table).getByRole('row', { name: /A\. P\., 1963/ })
    expect(alena).toHaveTextContent('C25')
    expect(alena).toHaveTextContent('nezaznamenáno') // T1: the first GP visit is not recorded
    expect(alena).toHaveTextContent(/RV-[0-9A-F]{12}/)
    expect(screen.getByText('Pojištěnci zdravotní pojišťovny 211')).toBeInTheDocument()
    // A closed case of the same insurer: T2 measured, T3 still running, feedback handed over.
    const benes = within(table).getByRole('row', { name: /K\. B\., 1949/ })
    expect(benes).toHaveTextContent('17 dní')
    expect(benes).toHaveTextContent('běží')
    expect(benes).toHaveTextContent('předána k doručení')
    // Other insurers (VZP 111, VoZP 201, …) are not listed; no names, birth dates, birth numbers or diagnosis text.
    expect(within(table).queryByRole('row', { name: /M\. K\., 1971/ })).toBeNull()
    const text = table.textContent ?? ''
    for (const leaked of [
      'Procházková',
      'Alena',
      '1963-07-22',
      '635722',
      'pankreatu',
      'Beneš',
      'tumor',
    ]) {
      expect(text).not.toContain(leaked)
    }
    expect(screen.getByText(/T1–T3 jsou orientační ukazatele/)).toBeInTheDocument()
  })

  it('every mock row satisfies the contract schema', async () => {
    setDemo({ role: 'reviewer', today: '2026-10-21' })
    const { data } = await client.GET('/api/reviewer/cases')
    expect(data?.length).toBeGreaterThan(0)
    for (const row of data ?? []) expect(() => reviewerCase.parse(row)).not.toThrow()
  })

  it('is refused to other roles, and the reviewer is refused the full case list', async () => {
    setDemo({ role: 'coordinator', today: '2026-10-21' })
    await expect(client.GET('/api/reviewer/cases')).rejects.toMatchObject({ status: 403 })
    setDemo({ role: 'reviewer', today: '2026-10-21' })
    await expect(client.GET('/api/cases')).rejects.toMatchObject({ status: 403 })
    renderRoute('/reviewer', { role: 'coordinator', today: '2026-10-21' })
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
