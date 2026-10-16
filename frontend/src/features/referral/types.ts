export interface ParsedReferral {
  filename: string
  patientName: string
  birthDate: string
  birthNumber: string
  insurer: string
  diagnosis: string
  urgent: boolean
  evidence: { docId: string; quote: string }
}
export interface Koc {
  id: string
  name: string
}
