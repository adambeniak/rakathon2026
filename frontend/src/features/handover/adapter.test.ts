import type { components } from '@/lib/api/schema'
import { adaptHandover, SECTION_KEYS } from './adapter'

type Handover = components['schemas']['Handover']

// Hand-written in the shape of contracts/openapi.json (not produced by the mocks), so this checks the real wire format.
const emptyField = { status: 'missing' as const, items: [], evidence: [], missing: [] }
const wire = (fields: Record<string, unknown>, rest: Partial<Handover> = {}): Handover => ({
  as_of: '2026-10-21T08:00:00+02:00',
  case_id: 'rakathon-2026-prochazkova',
  included_documents: ['10_Laborator_KOC2_2026-10-15'],
  excluded_documents: [{ doc_id: '12_Algeziologie_2026-10-26', reason: 'Dokument přijat po termínu as-of' }],
  fields: Object.fromEntries(SECTION_KEYS.map((k) => [k, fields[k] ?? emptyField])) as unknown as Handover['fields'],
  ...rest,
})

describe('adaptHandover', () => {
  it('reads as_of, fields and excluded_documents[].doc_id of the real response', () => {
    const v = adaptHandover(wire({}))
    expect(v.asOf).toBe('2026-10-21T08:00:00+02:00')
    expect(v.sections).toHaveLength(15)
    expect(v.excluded).toEqual([{ id: '12_Algeziologie_2026-10-26', reason: 'Dokument přijat po termínu as-of' }])
  })

  it('orders sections by number although the schema lists the fields alphabetically', () => {
    const v = adaptHandover(wire({}))
    expect(v.sections.map((s) => s.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    expect(v.sections[0]).toMatchObject({ key: '1_patient', title: 'Pacient' })
  })

  it('turns items into rows with unit, decimal comma, clinical date and per-value evidence', () => {
    const v = adaptHandover(
      wire({
        '13_labs': {
          status: 'complete',
          evidence: [{ doc_id: '10_Laborator_KOC2_2026-10-15', quote: 'CA 19-9 312,0 kU/l' }],
          items: [
            {
              label: 'CA 19-9',
              value: 312.5,
              unit: 'kU/l',
              clinical_date: '2026-10-15',
              evidence: [
                { doc_id: '10_Laborator_KOC2_2026-10-15', quote: 'CA 19-9 312,5 kU/l', authored_at: '2026-10-15', received_at: '2026-10-15T16:00:00+02:00' },
              ],
            },
          ],
          value_hash: 'abc',
        },
      }),
    )
    const labs = v.sections.find((s) => s.key === '13_labs')!
    expect(labs.rows).toEqual([
      {
        label: 'CA 19-9',
        value: '312,5 kU/l',
        note: '15. 10. 2026',
        evidence: [{ docId: '10_Laborator_KOC2_2026-10-15', quote: 'CA 19-9 312,5 kU/l' }],
        readOnly: undefined,
      },
    ])
    expect(labs.evidence).toEqual([{ docId: '10_Laborator_KOC2_2026-10-15', quote: 'CA 19-9 312,0 kU/l' }])
    expect(labs.valueHash).toBe('abc')
  })

  it('maps missing sub-items, conflicts and the section note, and never invents a value for a missing field', () => {
    const v = adaptHandover(
      wire({
        '9_performance_status': { ...emptyField, note: 'Uvedeno pouze „Soběstačná“; ECOG se nedovozuje.', conflicts: ['M1'], missing: ['ecog', 'tnm_clinical_stage'] },
      }),
    )
    const ps = v.sections.find((s) => s.key === '9_performance_status')!
    expect(ps).toMatchObject({ status: 'missing', rows: [], findingIds: ['M1'], note: 'Uvedeno pouze „Soběstačná“; ECOG se nedovozuje.' })
    expect(ps.missing).toEqual(['ecog', 'Klinické TNM']) // unknown keys are shown as delivered
  })

  it('reads the review state: confirmed by whom, edited, and a draft that is not confirmed', () => {
    const by = { display: 'MUDr. Havelka', id: 'havelka', role: 'koc_physician' }
    const v = adaptHandover(
      wire({
        '8_allergies': { ...emptyField, status: 'complete', review: { state: 'confirmed', by, edited: false } },
        '7_medications': { ...emptyField, status: 'complete', review: { state: 'draft', edited: true } },
      }),
    )
    expect(v.sections.find((s) => s.key === '8_allergies')).toMatchObject({ confirmed: true, confirmedBy: 'MUDr. Havelka', edited: undefined })
    expect(v.sections.find((s) => s.key === '7_medications')).toMatchObject({ confirmed: false, confirmedBy: undefined, edited: true })
  })

  it('marks consent rows with a source as read-only, other rows stay editable', () => {
    const ev = { doc_id: '04_PL_epikriza_2026-09-04', quote: 'Souhlasí se sdílením', authored_at: '2026-09-04', received_at: '2026-10-08T09:00:00+02:00' }
    const v = adaptHandover(
      wire({ '15_other': { ...emptyField, status: 'complete', items: [{ value: 'Souhlasí se sdílením informací.', evidence: [ev] }, { value: 'Bydlí sama.', evidence: [] }] } }),
    )
    const rows = v.sections.find((s) => s.key === '15_other')!.rows
    expect(rows.map((r) => r.readOnly)).toEqual([true, undefined])
  })

  it('shows the empty state (no sections) when no document is included, but still lists the excluded ones', () => {
    const v = adaptHandover(wire({}, { included_documents: [] }))
    expect(v.sections).toEqual([])
    expect(v.excluded).toHaveLength(1)
  })
})
