// Insurer (ZP 211) analytics over a simulated cohort. Operational wording only: no clinical judgement.
const plural = (n: number, one: string, few: string, many: string) =>
  n === 1 ? one : n >= 2 && n <= 4 ? few : many

export const insurer = {
  title: 'Analytika péče pro ZP 211',
  lead: 'Doby mezi kroky péče, čekání na vyšetření, vytížení koordinátorů a ilustrativní náklady podle nemocnic.',
  notice:
    'Simulovaná data – fiktivní kohorta pro demo, ilustrativní ceník. Nejde o skutečné úhrady ani hodnocení kvality péče.',
  asOf: (date: string) => `Stav dat k ${date}`,
  forbidden: 'Analytika péče je dostupná jen reviznímu lékaři zdravotní pojišťovny.',
  empty: 'Kohorta neobsahuje žádné případy',
  emptyHint: 'Jakmile budou k dispozici data o případech, zobrazí se zde.',
  notRecorded: 'nezaznamenáno',
  dash: '—',
  days: (n: number) => `${n} ${plural(n, 'den', 'dny', 'dní')}`,
  plusDays: (n: number) => `+${n} ${plural(n, 'den', 'dny', 'dní')}`,
  plusDaysAria: (n: number, from: string) =>
    `${n} ${plural(n, 'den', 'dny', 'dní')} od kroku ${from}`,
  facts: {
    heading: 'Přehled kohorty',
    cases: 'Případy v kohortě',
    casesValue: (all: number, simulated: number) => `${all} (z toho ${simulated} simulovaných)`,
    contactToMdt: 'Medián: kontakt PL → MDT',
    ctWait: 'Medián: CT od objednání',
    biopsyWait: 'Medián: biopsie od objednání',
  },
  hospitals: {
    heading: 'Nemocnice podle provozního indikátoru',
    caption:
      'Nemocnice seřazené podle provozního indikátoru 0–100 (nejde o hodnocení kvality péče). Doby jsou mediány ve dnech (kalendářní dny, Europe/Prague).',
    cols: {
      rank: 'Pořadí (provozní indikátor)',
      hospital: 'Nemocnice',
      cases: 'Případy',
      ct: 'CT: objednání → provedení (dny)',
      biopsy: 'Biopsie: objednání → provedení (dny)',
      mdt: 'Kontakt PL → MDT (dny)',
      treatment: 'MDT → zahájení léčby (dny)',
      cost: 'Medián nákladů na případ',
      minutes: 'Koordinátor (min/pacient)',
      utilisation: 'Vytížení koordinátorů',
      indicator: 'Provozní indikátor (0–100)',
    },
    badges: { fastest: 'Nejrychlejší v kohortě', lowest_cost: 'Nejnižší náklady v kohortě' },
    simulated: 'simulace',
  },
  formula: {
    summary: 'Jak se provozní indikátor počítá',
    weights: (speed: string, cost: string, target: string) =>
      `Váhy: rychlost ${speed}, náklady ${cost}, podíl případů v cílových lhůtách ${target}.`,
    targets: (ct: number, biopsy: number) =>
      `Cílové lhůty pro demo (nejde o klinický standard): CT do ${ct} dní od objednání a biopsie do ${biopsy} dní od objednání.`,
    capacity: (minutes: number, from: string, to: string, weeks: string) =>
      `Kapacita koordinátora: ${minutes} min týdně; období ${from} – ${to} (${weeks} týdnů).`,
    assumption: 'Předpoklad pro demo',
    priceList: 'Ilustrativní ceník',
    priceCols: { item: 'Položka', price: 'Cena' },
  },
  coordinators: {
    heading: 'Koordinátoři',
    caption: 'Případy, čas koordinátora na pacienta a vytížení vůči předpokládané kapacitě.',
    cols: {
      name: 'Koordinátor/ka',
      hospital: 'Nemocnice',
      cases: 'Případy',
      minutes: 'Medián min/pacient',
      accepted: 'Medián kontakt PL → převzetí (dny)',
      utilisation: 'Vytížení',
    },
  },
  journeys: {
    heading: 'Cesty pacientů',
    hint: 'Data jednotlivých kroků a počet dní mezi nimi. Chybějící údaj se nedopočítává.',
    demo: 'Demo případ',
    simulated: 'Simulace',
    showSimulated: (n: number) => `Simulované cesty (${n})`,
    coordinator: (name: string) => `Koordinace: ${name}`,
    cost: (value: string) => `Ilustrativní náklady: ${value}`,
    milestones: {
      gp_contacted_coordinator: 'Kontakt PL → koordinátor',
      accepted: 'Převzetí',
      ct_done: 'CT',
      biopsy_done: 'Biopsie',
      mdt: 'MDT',
      treatment_start: 'Zahájení léčby',
    },
  },
} as const
