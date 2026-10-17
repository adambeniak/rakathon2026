import { adaptHandover } from '@/features/handover/adapter'
import { api } from '@/lib/api/http'
import { setDemo } from '@/lib/demo'
import type { components } from '@/lib/api/schema'
import type { SectionView as HandoverSection } from '@/features/handover/types'
import { resetStore } from '../fixtures/store'

const CASE = '/api/cases/rakathon-2026-prochazkova'
type Wire = components['schemas']['Handover']

const section = (sections: HandoverSection[], key: string) => sections.find((s) => s.key === key)!
const handover = async () => adaptHandover(await api.get<Wire>(`${CASE}/handover`))

const confirmBody = (sec: HandoverSection, extra: Record<string, unknown> = {}) => ({ expected_value_hash: sec.valueHash, ...extra })

describe('section review in the mock handover (contract confirm route)', () => {
  beforeEach(() => {
    resetStore()
    setDemo({ role: 'physician', today: '2026-10-21' })
  })

  it('has no bulk confirmation and no provisional edit route', async () => {
    await expect(api.post(`${CASE}/handover/confirm-all`)).rejects.toBeDefined()
    await expect(api.post(`${CASE}/handover/sections/8_allergies/edit`, { rows: {}, reason: 'x' })).rejects.toBeDefined()
  })

  it('answers a confirmation with the whole handover and the section confirmed', async () => {
    const sec = section((await handover()).sections, '8_allergies')
    const wire = await api.post<Wire>(`${CASE}/handover/sections/${sec.number}/confirm`, confirmBody(sec))
    expect(section(adaptHandover(wire).sections, '8_allergies')).toMatchObject({ confirmed: true, acceptedMissing: false })
  })

  it('refuses a missing section without accept_missing or a value, and accept_missing on a section that is not missing', async () => {
    const view = (await handover()).sections
    const ecog = section(view, '9_performance_status')
    const allergies = section(view, '8_allergies')
    expect(ecog.status).toBe('missing')
    await expect(api.post(`${CASE}/handover/sections/9/confirm`, confirmBody(ecog))).rejects.toMatchObject({ status: 409 })
    await expect(api.post(`${CASE}/handover/sections/8/confirm`, confirmBody(allergies, { accept_missing: true }))).rejects.toMatchObject({ status: 409 })
  })

  it('accept_missing counts as reviewed and is reported as accepted_missing', async () => {
    const ecog = section((await handover()).sections, '9_performance_status')
    await api.post(`${CASE}/handover/sections/9/confirm`, confirmBody(ecog, { accept_missing: true }))
    expect(section((await handover()).sections, '9_performance_status')).toMatchObject({ confirmed: true, acceptedMissing: true })
  })

  it('an edited value is saved and confirmed in one call and shown as edited by the physician', async () => {
    const sec = section((await handover()).sections, '8_allergies')
    await api.post(`${CASE}/handover/sections/8/confirm`, confirmBody(sec, { edited_value: 'Bez známých alergií' }))
    const edited = section((await handover()).sections, '8_allergies')
    expect(edited).toMatchObject({ confirmed: true, edited: true, editableText: 'Bez známých alergií' })
    expect(edited.rows).toEqual([expect.objectContaining({ label: 'Upraveno lékařem', value: 'Bez známých alergií', evidence: undefined })])
  })

  it('refuses an edited value for a section whose value is not plain text', async () => {
    const sec = section((await handover()).sections, '7_medications')
    await expect(api.post(`${CASE}/handover/sections/7/confirm`, confirmBody(sec, { edited_value: 'x' }))).rejects.toMatchObject({ status: 422 })
  })

  it('refuses a confirmation of a value that changed since the physician saw it', async () => {
    const shown = section((await handover()).sections, '8_allergies')
    await api.post(`${CASE}/handover/sections/8/confirm`, confirmBody(shown, { edited_value: 'Bez známých alergií' }))
    await expect(api.post(`${CASE}/handover/sections/8/confirm`, confirmBody(shown))).rejects.toMatchObject({ status: 409 })
  })
})
