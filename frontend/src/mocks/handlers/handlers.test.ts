import { adaptHandover } from '@/features/handover/adapter'
import { api } from '@/lib/api/http'
import { setDemo } from '@/lib/demo'
import type { components } from '@/lib/api/schema'
import type { HandoverSection } from '@/lib/domain'
import { resetStore } from '../fixtures/store'

const CASE = '/api/cases/rakathon-2026-prochazkova'
type Wire = components['schemas']['Handover']

const section = (sections: HandoverSection[], key: string) => sections.find((s) => s.key === key)!
const handover = async () => adaptHandover(await api.get<Wire>(`${CASE}/handover`))

describe('clinician edits in the mock handover', () => {
  beforeEach(() => {
    resetStore()
    setDemo({ role: 'physician', today: '2026-10-21' })
  })

  it('keeps the reason, author and time of every corrected row', async () => {
    await api.post(`${CASE}/handover/sections/10_weight_height/edit`, { rows: { 0: '171 cm' }, reason: 'Změřeno při příjmu' })
    await api.post(`${CASE}/handover/sections/10_weight_height/edit`, { rows: { 1: '61 kg' }, reason: 'Převáženo na oddělení' })
    const [height, weight] = section((await handover()).sections, '10_weight_height').rows
    expect(height).toMatchObject({ value: '171 cm' })
    expect(height?.note).toContain('Změřeno při příjmu')
    expect(weight).toMatchObject({ value: '61 kg' })
    expect(weight?.note).toContain('Převáženo na oddělení')
    expect(weight?.note).not.toContain('Změřeno při příjmu')
  })

  it('edit → reconfirm → MDT shows the corrected value, not the original', async () => {
    const original = section((await handover()).sections, '8_allergies').rows[0]!.value
    await api.post(`${CASE}/handover/sections/8_allergies/edit`, { rows: { 0: 'Bez známých alergií' }, reason: 'Upřesněno s pacientkou' })
    // The contract confirms by section number and returns the hash of the value as shown.
    const edited = section((await handover()).sections, '8_allergies')
    await api.post(`${CASE}/handover/sections/${edited.number}/confirm`, { expected_value_hash: edited.valueHash })
    const mdt = await api.get<{ sections: HandoverSection[] }>(`${CASE}/mdt`)
    const allergies = section(mdt.sections, '8_allergies')
    expect(original).not.toBe('Bez známých alergií')
    expect(allergies.confirmed).toBe(true)
    expect(allergies.rows[0]).toMatchObject({ value: 'Bez známých alergií' })
    expect(allergies.rows[0]?.note).toContain('Upřesněno s pacientkou')
  })

  it('refuses a confirmation of a value that changed since the physician saw it', async () => {
    const shown = section((await handover()).sections, '8_allergies')
    await api.post(`${CASE}/handover/sections/8_allergies/edit`, { rows: { 0: 'Bez známých alergií' }, reason: 'Upřesněno s pacientkou' })
    await expect(
      api.post(`${CASE}/handover/sections/${shown.number}/confirm`, { expected_value_hash: shown.valueHash }),
    ).rejects.toMatchObject({ status: 409 })
  })
})
