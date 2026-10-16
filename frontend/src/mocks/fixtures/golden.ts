import raw from './handover.golden.json'

interface GoldenEvidence {
  doc: string
  quote?: string
}
interface GoldenField {
  status: string
  value?: unknown
  missing?: string[]
  conflicts?: string[]
  evidence?: GoldenEvidence[]
  key_values?: Array<{ test: string; value: number; unit: string; flag?: string; date: string; doc: string }>
  must_mention?: string[]
  context?: string
}
interface GoldenFinding {
  id: string
  kind: string
  severity: 'high' | 'medium' | 'low' | 'info'
  docs?: string[]
  quotes?: string[]
  field?: string
  note?: string
}

export const golden = raw as unknown as {
  as_of_timestamp: string
  fields: Record<string, GoldenField>
  expected_findings: GoldenFinding[]
  timeline: Array<{ date: string; event: string; precision?: string }>
  intervals_days: Record<string, number>
}
