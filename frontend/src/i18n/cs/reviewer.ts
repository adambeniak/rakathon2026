export const reviewer = {
  title: 'Přehled pro revizního lékaře ZP 211',
  hint: 'Minimální souhrn bez identifikace pacienta a bez klinického obsahu. Jen stav a časové intervaly.',
  cols: { patient: 'Pacient (zkratka, rok narození)', diagnosis: 'Diagnóza (MKN-10)', state: 'Stav', referred: 'Žádost do KOC', t1: 'T1', t2: 'T2', t3: 'T3' },
  empty: 'Žádné případy pojištěnců ZP 211',
  emptyHint: 'Případy se zobrazí po odeslání žádosti praktickým lékařem.',
  pending: '—',
} as const
