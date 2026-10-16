export interface ParsedReferral {
  filename: string
  patientName: string
  birthDate: string
  birthNumber: string
  insurer: string
  diagnosis: string
  urgent: boolean
  evidence: Record<'patientName' | 'birthDate' | 'birthNumber' | 'insurer' | 'diagnosis' | 'urgent', ReferralEvidence>
}
import type { DocumentInfo } from '@/lib/domain'

export interface ReferralEvidence {
  docId: string
  quote: string
  doc: DocumentInfo
}
export interface Koc {
  id: string
  name: string
}
