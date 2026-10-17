import { cs } from './cs'

function strings(node: unknown, path: string, out: [string, string][]): [string, string][] {
  if (typeof node === 'string') out.push([path, node])
  else if (node && typeof node === 'object') for (const [k, v] of Object.entries(node)) strings(v, `${path}.${k}`, out)
  return out
}

describe('approved clinician-review wording', () => {
  // Approved: "Potvrzeno lékařem", "Upraveno lékařem", "Ponecháno jako chybějící". Never claim the AI output is
  // "ověřeno" / "zkontrolováno" (nothing here verifies clinical truth).
  it('has no UI string that says "Ověřeno" or "Zkontrolováno"', () => {
    const bad = strings(cs, 'cs', []).filter(([, text]) => /ověřen|zkontrolován/i.test(text))
    expect(bad).toEqual([])
  })
})
