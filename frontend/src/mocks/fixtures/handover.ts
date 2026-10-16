import type { HandoverSection, HandoverStatus } from '@/lib/domain'
import { formatDate } from '@/lib/date'
import { golden } from './golden'

type Row = HandoverSection['rows'][number]
type Gf = (typeof golden.fields)[string]

const TITLES: Record<string, string> = {
  '1_patient': 'Pacient',
  '2_contacts': 'Kontakty',
  '3_diagnosis': 'Diagnóza',
  '4_epicrisis': 'Epikríza',
  '5_mdt_question': 'Otázka pro MDT',
  '6_comorbidities': 'Komorbidity',
  '7_medications': 'Léková anamnéza',
  '8_allergies': 'Alergie',
  '9_performance_status': 'Stav výkonnosti',
  '10_weight_height': 'Výška a hmotnost',
  '11_symptoms': 'Symptomy',
  '12_examinations': 'Provedená vyšetření',
  '13_labs': 'Laboratoř',
  '14_histology': 'Histologie',
  '15_other': 'Jiná sdělení',
}

const FINDING_LINKS: Record<string, string[]> = {
  '2_contacts': ['M3'],
  '3_diagnosis': ['M2'],
  '5_mdt_question': ['Q1'],
  '7_medications': ['C1'],
  '9_performance_status': ['M1'],
  '10_weight_height': ['S1'],
  '14_histology': ['C2'],
}

const S = (v: unknown): string => (v === null || v === undefined ? '' : String(v))
const obj = (v: unknown): Record<string, unknown> => (v ?? {}) as Record<string, unknown>
const arr = (v: unknown): Array<Record<string, unknown>> => (Array.isArray(v) ? (v as Array<Record<string, unknown>>) : [])

const SEX: Record<string, string> = { female: 'žena', male: 'muž' }

function rowsFor(key: string, f: Gf): Row[] {
  const v = obj(f.value)
  switch (key) {
    case '1_patient':
      return [
        { label: 'Jméno', value: `${S(v.given)} ${S(v.family)}` },
        { label: 'Pohlaví', value: SEX[S(v.sex)] ?? S(v.sex) },
        { label: 'Narození', value: `${formatDate(S(v.birth_date))} (${S(v.age_years)} let)` },
        { label: 'Rodné číslo', value: S(v.birth_number), note: v.birth_number_checksum_valid ? 'kontrolní součet v pořádku' : undefined },
        { label: 'Pojišťovna', value: `${S(v.insurer_code)} – ${S(v.insurer_name)}` },
        { label: 'Adresa', value: S(v.address) },
      ]
    case '2_contacts': {
      const c = obj(v.contact_person)
      return [
        { label: 'Telefon pacientky', value: S(v.patient_phone) },
        { label: 'Kontaktní osoba', value: `${S(c.name)} (${S(c.relation)}), ${S(c.phone)}` },
      ]
    }
    case '3_diagnosis':
      return [
        { label: 'MKN-10', value: S(v.icd10) },
        { label: 'Popis', value: S(v.text) },
        { label: 'MKN-O morfologie', value: S(v.icdo3_morphology) },
        { label: 'Histologicky ověřeno', value: formatDate(S(v.verified_histologically_on)) },
      ]
    case '4_epicrisis':
      return [
        {
          value:
            'V dokumentaci uvedeno: od poloviny srpna 2026 bolesti v epigastriu, v laboratoři cholestáza; UZ břicha 29. 9. 2026 – ložisko hlavy pankreatu suspektní z malignity; CT 8. 10. 2026 – tumor hlavy pankreatu 35 mm; EUS-FNB 12. 10. 2026; histologie vydána 19. 10. 2026 – duktální adenokarcinom; CA 19-9 312 kU/l (15. 10. 2026).',
        },
      ]
    case '5_mdt_question':
      return [{ value: S(f.value) }]
    case '6_comorbidities':
      return arr(f.value).map((c) => ({ value: S(c.text), note: [c.icd10, c.detail].filter(Boolean).join(' · ') || undefined }))
    case '7_medications':
      return arr(f.value).map((m) => ({ label: S(m.drug), value: `${S(m.dose)}, ${S(m.schedule)}` }))
    case '8_allergies':
      return [{ value: S(f.value) }]
    case '9_performance_status':
      return [{ value: 'Neuvedeno', note: f.context }]
    case '10_weight_height': {
      return [
        { label: 'Výška', value: `${S(v.height_cm)} cm`, note: formatDate(S(v.height_date)) },
        ...arr(v.weights).map((w) => ({ label: 'Hmotnost', value: `${S(w.kg)} kg`, note: formatDate(S(w.date)) })),
      ]
    }
    case '11_symptoms':
      return [
        { label: 'Začátek', value: S(v.onset) },
        ...((v.items as string[] | undefined) ?? []).map((i) => ({ value: i })),
      ]
    case '12_examinations':
      return arr(f.value).map((e) => ({ label: formatDate(S(e.date)), value: `${S(e.type)} – ${S(e.place)}` }))
    case '13_labs':
      return (f.key_values ?? []).map((l) => ({
        label: `${l.test} (${formatDate(l.date)})`,
        value: `${String(l.value).replace('.', ',')} ${l.unit}${l.flag ? ` ${l.flag}` : ''}`,
      }))
    case '14_histology': {
      const ihc = obj(v.ihc)
      return [
        { label: 'Číslo nálezu', value: S(v.report_id) },
        { label: 'Vydáno', value: formatDate(S(v.issued)) },
        { label: 'Grade', value: S(v.grade) },
        { label: 'Perineurální invaze', value: v.perineural_invasion ? 'ano' : 'ne' },
        { label: 'IHC', value: Object.entries(ihc).map(([k, x]) => `${k} ${S(x)}`).join(', ') },
      ]
    }
    case '15_other':
      return ((f.value as string[] | undefined) ?? []).map((i) => ({ value: i }))
    default:
      return []
  }
}

const MISSING_LABEL: Record<string, string> = {
  patient_email: 'E-mail pacientky',
  tnm_clinical_stage: 'Klinické TNM',
}

export function buildSections(confirmed: Record<string, string>): HandoverSection[] {
  return Object.entries(golden.fields).map(([key, f]) => {
    const number = Number(key.split('_')[0])
    return {
      key,
      number,
      title: TITLES[key] ?? key,
      status: f.status as HandoverStatus,
      rows: rowsFor(key, f),
      missing: (f.missing ?? []).map((m) => MISSING_LABEL[m] ?? m),
      evidence: [
        ...(f.evidence ?? []).map((e) => ({ docId: e.doc, quote: e.quote })),
        ...(f.key_values
          ? [...new Set(f.key_values.map((k) => k.doc))].map((docId) => ({ docId }))
          : []),
        ...(key === '12_examinations'
          ? [...new Set(arr(f.value).map((e) => S(e.doc)))].map((docId) => ({ docId }))
          : []),
      ],
      findingIds: FINDING_LINKS[key] ?? [],
      confirmed: key in confirmed,
      confirmedBy: confirmed[key],
    }
  })
}

export const CONFIRMABLE = (s: HandoverSection): boolean => s.status !== 'missing'
