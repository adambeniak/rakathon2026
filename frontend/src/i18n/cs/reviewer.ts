export const reviewer = {
  title: 'Přehled pro revizního lékaře',
  insurer: (code: string) => `Pojištěnci zdravotní pojišťovny ${code}`,
  hint: 'Omezený souhrn: iniciály, rok narození, skupina diagnózy z žádosti PL, stav případu, časové intervaly a stav předání zpětné vazby. Bez jmen, rodných čísel a bez klinického textu.',
  proxies:
    'T1–T3 jsou zástupné hodnoty: T1 první návštěva PL → žádost do KOC, T2 žádost do KOC → MDT, T3 MDT → onkologické konzilium. „Nezaznamenáno“: výchozí bod není v systému zapsán.',
  caption: 'Případy pojištěnců',
  cols: {
    patient: 'Pacient (iniciály, rok narození)',
    ref: 'Označení případu',
    diagnosis: 'Skupina dg. dle žádosti PL (MKN-10)',
    state: 'Stav',
    referred: 'Žádost do KOC',
    t1: 'T1',
    t2: 'T2',
    t3: 'T3',
    delivery: 'Zpětná vazba PL',
  },
  delivery: {
    not_sent: 'zatím neodeslána',
    handed_over: 'předána k doručení',
    opened_by_gp: 'otevřena PL',
    unconfirmed: 'předání nepotvrzeno',
  },
  openedOn: (date: string) => `otevřena PL ${date}`,
  empty: 'Žádné případy pojištěnců vaší pojišťovny',
  emptyHint: 'Případy se zobrazí po odeslání žádosti praktickým lékařem.',
  pending: '—',
} as const
