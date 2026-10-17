import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page } from '@playwright/test'

const RAW = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../data/raw/Pacient')
// Step 3: the reports requested in step 2 (01, 02, 03, 05, 06) together with 04 and 08–11, under their original names.
const UPLOADS = [
  '01_Kardiologie_2026-07-20',
  '02_Laborator_2026-09-01',
  '03_RTG_plic_2026-09-03',
  '04_PL_epikriza_2026-09-04',
  '05_Gastroenterologie_2026-09-15',
  '06_UZ_bricha_2026-09-29',
  '08_CT_KOC1_2026-10-08',
  '09_Biopsie_vykon_KOC2_2026-10-12',
  '10_Laborator_KOC2_2026-10-15',
  '11_Histologie_KOC2_2026-10-19',
]
const REQUESTED = ['01_', '02_', '03_', '05_', '06_']
// The mock case id; the live backend appends a random suffix (`rakathon-2026-prochazkova-<6 hex>`), read from the URL.
const MOCK_CASE_ID = 'rakathon-2026-prochazkova'
// Project `live` (E2E_BASE_URL): Mailpit's HTTP API of the local stack (`make up-local`).
const MAILPIT = process.env.E2E_MAILPIT_URL ?? 'http://localhost:8025'
// Step 3b: reports 12 and 13 arrive after the MDT (28. 10.; no switcher preset, so the demo clock API is used).
const LATE_UPLOADS = ['12_Algeziologie_2026-10-26', '13_Psychologie_KOC2_2026-10-27']
const CONCLUSION = 'Závěr MDT – fiktivní text pro automatický test (bez klinického obsahu).'
const report = (name: string) => path.join(RAW, `${name}.docx`)

async function asRole(page: Page, role: string) {
  await page.getByLabel('Role').selectOption({ label: role })
}
function nav(page: Page, name: string) {
  return page.getByRole('navigation', { name: 'Hlavní navigace' }).getByRole('link', { name })
}
function tab(page: Page, name: string) {
  return page.getByRole('navigation', { name: 'Záložky případu' }).getByRole('link', { name })
}
/** A handover section; its accessible name is "<number><title>". */
function section(page: Page, title: string) {
  return page.getByRole('region', { name: new RegExp(`^\\d+${title}$`) })
}
async function openCase(page: Page) {
  await nav(page, 'Fronta případů').click()
  await page.getByRole('link', { name: 'Alena Procházková' }).click()
}
function caseState(page: Page) {
  return page.getByText('Stav případu:').locator('..')
}
async function atDate(page: Page, label: string) {
  const date = page.getByLabel('Simulované datum')
  await date.selectOption({ label })
  // Live: the switcher first moves the server clock (PUT /api/demo/clock) and shows the day only once it answered; the
  // day is part of the query keys, so a click before that lands on a view that is about to re-render.
  await expect(date.locator('option:checked')).toHaveText(label)
  await expect(page.getByText('Demo: simulované datum:').getByText(label)).toBeVisible()
}
/** Live only: a demo endpoint the runbook calls with curl (clock without a preset, story replay), then a reload. */
async function demoApi(page: Page, method: 'PUT' | 'POST', url: string, data?: object) {
  const res = await page.request.fetch(url, {
    method,
    headers: { 'X-Demo-Role': 'coordinator' },
    data,
  })
  expect(res.ok(), `${method} ${url} answered ${res.status()}: ${await res.text()}`).toBe(true)
  await page.reload()
}
async function uploadReports(page: Page, names: string[], requested: string[]) {
  const upload = page.getByRole('region', { name: 'Přidat zprávu k případu' })
  await upload.getByLabel('Soubor zprávy').setInputFiles(names.map(report))
  // Each requested report is matched to its open request by the examination date; the rest stay unmatched. With no
  // open request left (step 3b) the form shows no request picker at all.
  for (const name of requested.length > 0 ? names : []) {
    const matched = requested.some((r) => name.startsWith(r))
    const select = upload.getByLabel(`Požadavek pro ${name}.docx`)
    if (matched) await expect(select).not.toHaveValue('')
    await expect(select.locator('option:checked')).toHaveText(
      matched ? /\d{4}|\d\. \d+\. 2026/ : 'Bez požadavku',
    )
  }
  await upload.getByRole('button', { name: 'Nahrát' }).click()
  // Live: the files go up one by one (~2–3 s each on a busy machine) and the results show once all are done.
  await expect(upload.getByRole('button', { name: 'Nahrát' })).toBeVisible({ timeout: 180_000 })
  for (const name of names) await expect(upload.getByText(`Nahráno: ${name}.docx`)).toBeVisible()
}

test('demo flow', async ({ page }) => {
  // `mock`: MSW in the page. `live`: a running app on a fresh `make up-local` (demo-start), driven like the runbook.
  const live = test.info().project.name === 'live'
  let caseId = MOCK_CASE_ID
  if (live) expect((await page.request.delete(`${MAILPIT}/api/v1/messages`)).ok()).toBe(true)
  await page.goto('/')
  await test.step('1 · Referral without a form', async () => {
    await atDate(page, '2. 10. 2026')
    await asRole(page, 'Praktický lékař')
    await nav(page, 'Nová žádost').click()
    await page.getByLabel('Soubor žádosti').setInputFiles(report('07_PL_zadost_KOC2_2026-10-02'))
    const summary = page.getByRole('region', { name: 'Předvyplněný souhrn' })
    await expect(summary).toBeVisible()
    await expect(summary.getByText('Alena Procházková')).toBeVisible()
    await expect(summary.getByText('635722/1013')).toBeVisible()
    await expect(summary.getByText('C25.0 – suspektní tumor hlavy pankreatu')).toBeVisible()
    await page
      .getByLabel('Cílové onkologické centrum')
      .selectOption({ label: 'KOC 2 – Komplexní onkologické centrum Nemocnice Lipová' })
    await expect(page.getByLabel('Naléhavost žádosti (potvrďte)')).toHaveValue('urgent')
    await page
      .getByRole('checkbox', {
        name: 'Pacient/ka souhlasí se sdílením zdravotnické dokumentace s vybraným centrem.',
      })
      .check()
    await page.getByRole('button', { name: 'Odeslat do KOC' }).click()
    await expect(page.getByRole('heading', { name: 'Odesláno' })).toBeVisible()
    await page.getByRole('link', { name: 'Přejít na moje pacienty' }).click()
    const row = page.getByRole('row', { name: /Alena Procházková/ })
    await expect(row.getByRole('cell', { name: 'Odesláno', exact: true })).toBeVisible()
    // The live API names the role-level holder ("Koordinátor KOC 2") until a person accepts; the mock a person-like label.
    await expect(row).toContainText(/koordinátor(ka)? KOC 2/i)
  })

  await test.step('2 · Triage and missing documents', async () => {
    await asRole(page, 'Koordinátorka KOC 2')
    const newColumn = page.getByRole('region', { name: /^Nový/ })
    const card = newColumn.getByRole('article', { name: 'Alena Procházková' })
    await card.getByRole('button', { name: 'Převzít případ: Alena Procházková' }).click()
    await expect(page.getByRole('article', { name: 'Alena Procházková' })).toContainText('V triage')
    await page.getByRole('link', { name: 'Alena Procházková' }).click()
    await expect(page).toHaveURL(/\/cases\/rakathon-2026-prochazkova[^/]*$/)
    caseId = new URL(page.url()).pathname.split('/')[2]
    await page.getByRole('link', { name: 'Vyžádat podklady' }).click()
    const triage = page
      .getByRole('region')
      .filter({ has: page.getByRole('heading', { name: 'Chybějící podklady k vyžádání' }) })
      .last()
    await expect(triage.getByText('Návrh k vyžádání – zkontrolujte a odešlete.')).toBeVisible()
    await expect(triage.getByRole('checkbox')).toHaveCount(5)
    // All proposals come preselected, so the panel shows no "Vybrat vše" button (runbook drift, #176).
    for (const box of await triage.getByRole('checkbox').all()) await expect(box).toBeChecked()
    await triage.getByRole('button', { name: 'Vyžádat vybrané' }).click()
    await expect(page.getByText('Vyžádáno: 5.')).toBeVisible()
    await expect(caseState(page)).toContainText('Čeká na podklady')
  })

  await test.step('3 · Handover extraction (uploads as coordinator)', async () => {
    await atDate(page, '20. 10. 2026')
    await tab(page, 'Dokumenty').click()
    await uploadReports(page, UPLOADS, REQUESTED)
    // The last open request is closed, so the case is complete (the mock keeps its date-driven state).
    if (live) await expect(caseState(page)).toContainText('Kompletní')
    if (live) {
      // 3b: reports 12 and 13 at 28. 10. (before the pathway launch, so the watchdog escalates nothing), then back.
      await demoApi(page, 'PUT', '/api/demo/clock', { now: '2026-10-28T09:00:00+01:00' })
      await uploadReports(page, LATE_UPLOADS, [])
      await atDate(page, '20. 10. 2026')
    }
  })

  await test.step('3 · Handover extraction (review as physician)', async () => {
    await tab(page, 'Handover').click()
    const summary = page.getByRole('group', { name: 'Souhrn handoveru' })
    await expect(summary).toContainText('Potvrzeno lékařem: 0 z 15')
    await expect(page.getByText(/^Stav k termínu:/)).toBeVisible()
    await expect(page.getByRole('region', { name: /^\d+\D/ })).toHaveCount(15)
    await expect(section(page, 'Stav výkonnosti')).toContainText('Chybí')
    await expect(section(page, 'Léková anamnéza')).toContainText('Nesouhlasí')
    await expect(section(page, 'Výška a hmotnost')).toContainText('Zastaralé')
    await expect(section(page, 'Pacient')).toContainText('Návrh AI – čeká na potvrzení')
    // The coordinator cannot confirm.
    await expect(
      page.getByText('Potvrdit sekci může pouze lékař. Přepněte roli na „Lékař KOC 2“.'),
    ).toBeVisible()
    await expect(
      section(page, 'Pacient').getByRole('button', { name: 'Potvrdit sekci: Pacient' }),
    ).toBeDisabled()
    // Evidence of one value: document, authored, received and the verbatim quote.
    await section(page, 'Pacient')
      .getByRole('button', { name: /^Zdroj: Žádost PL/ })
      .first()
      .click()
    const evidence = page.getByRole('dialog')
    await expect(evidence).toContainText('Vyhotoveno')
    await expect(evidence).toContainText('Přijato')
    await expect(evidence).toContainText('Citace z dokumentu')
    await expect(evidence.getByRole('blockquote')).toContainText('22. 7. 1963 (63 let)')
    await evidence.getByRole('button', { name: 'Zavřít' }).first().click()
    await expect(evidence).toBeHidden()

    await asRole(page, 'Lékař KOC 2')
    await openCase(page)
    await tab(page, 'Handover').click()
    await section(page, 'Pacient').getByRole('button', { name: 'Potvrdit sekci: Pacient' }).click()
    await expect(summary).toContainText('Potvrzeno lékařem: 1 z 15')
    await expect(section(page, 'Pacient')).toContainText('Potvrzeno lékařem')
    await expect(section(page, 'Pacient')).toContainText(
      'Potvrdil(a) doc. MUDr. Pavel Hrubý, Ph.D.',
    )
    await expect(
      section(page, 'Léková anamnéza').getByRole('list', { name: 'Související zjištění' }),
    ).toContainText('Nesoulad mezi datem výkonu')
  })

  await test.step('4 · Coordination: who holds the baton', async () => {
    await atDate(page, '2. 10. 2026')
    await asRole(page, 'Koordinátorka KOC 2')
    await openCase(page)
    await tab(page, 'Úkoly').click()
    await page
      .getByRole('button', { name: 'Spustit sadu: Karcinom pankreatu – diagnostika' })
      .click()
    const launch = page.getByRole('form', {
      name: 'Spustit sadu: Karcinom pankreatu – diagnostika',
    })
    await expect(launch.getByLabel('Indikující lékař KOC').locator('option:checked')).toHaveText(
      /doc\. MUDr\. Pavel Hrubý, Ph\.D\./,
    )
    await expect(launch.getByLabel('Začátek sady')).toHaveValue('2026-10-02')
    await expect(launch.getByLabel('Plánovaný začátek MDT')).toHaveValue('2026-10-21T08:00')
    await launch.getByRole('button', { name: 'Spustit sadu', exact: true }).click()
    const board = page.getByRole('group', { name: 'Kdo je na tahu' })
    for (const lane of ['PL', 'Koordinátor', 'Lékař KOC', 'Externí pracoviště', 'Pacient'])
      await expect(board.getByRole('region', { name: lane, exact: true })).toBeVisible()
    const external = board.getByRole('region', { name: 'Externí pracoviště' })
    await expect(external).toContainText('CT hrudníku a břicha (pankreatický protokol)')
    await expect(external).toContainText('Čeká na: EUS-FNB')
    await expect(board).toContainText('Termín 8. 10. 2026')

    // A manual order confirmation on a step the story does not replay.
    await board
      .getByRole('button', { name: 'Potvrdit objednání: Algeziologické vyšetření' })
      .click()
    const order = board.getByRole('form', { name: 'Potvrdit objednání: Algeziologické vyšetření' })
    await order.getByLabel('Pracoviště').fill('KOC 2 – Nemocnice Lipová, algeziologie')
    await order.getByLabel('Datum vyšetření').fill('2026-10-26')
    await order.getByRole('button', { name: 'Potvrdit', exact: true }).click()
    const algo = board.getByRole('listitem').filter({ hasText: 'Algeziologické vyšetření' })
    await expect(algo).toContainText('Objednáno')
    await expect(algo).toContainText('KOC 2 – Nemocnice Lipová, algeziologie')

    // Escalation day. Live: `POST /api/demo/advance` replays the story to 16. 10. (as in the runbook). The mock does not
    // implement it; the date switcher is enough there, because the mock derives the task phases from the date (#175).
    if (live) await demoApi(page, 'POST', `/api/demo/advance?case_id=${caseId}&to=2026-10-16`)
    else await atDate(page, '16. 10. 2026')
    const histology = board.getByRole('listitem').filter({ hasText: /^Histologie/ })
    await expect(histology).toContainText('Slíbeno do 15. 10. 2026')
    await expect(histology).toContainText('Po termínu')
    await expect(histology).toContainText('1 pracovní den')
    await expect(histology).toContainText('Eskalováno 16. 10. 2026')
    await expect(board.getByText('Po termínu')).toHaveCount(1)
  })

  // The runbook marks the case ready at 21. 10. (live). The mock already reports `pripraveno_mdt` on that day and
  // accepts `mark_ready_mdt` only in `kompletni` (19.–20. 10.), so in mock mode the readiness gate runs at 20. 10. (#172).
  await test.step(`5 · MDT handover: readiness gate with a waived missing item (${live ? '21. 10.' : 'mock: 20. 10.'})`, async () => {
    if (live) {
      await atDate(page, '21. 10. 2026')
      // Report 11 is in the case since step 3: replaying to 21. 10. 09:00 delivers the histology result at once instead
      // of at the next watchdog round (#132).
      await demoApi(
        page,
        'POST',
        `/api/demo/advance?case_id=${caseId}&to=2026-10-21T09:00:00%2B02:00`,
      )
      const board = page.getByRole('group', { name: 'Kdo je na tahu' })
      await expect(board.getByRole('listitem').filter({ hasText: /^Histologie/ })).toContainText(
        'Výsledek doručen',
      )
      await expect(board.getByText('Po termínu')).toHaveCount(0)
    } else await atDate(page, '20. 10. 2026')
    await asRole(page, 'Lékař KOC 2')
    await openCase(page)
    await tab(page, 'Handover').click()
    const summary = page.getByRole('group', { name: 'Souhrn handoveru' })
    if (live) {
      // A new snapshot as of the MDT start (#122): confirming one section persists the handover the gate reads.
      await expect(page.getByText('Stav k termínu: 21. 10. 2026 8:00')).toBeVisible()
      await expect(summary).toContainText('Potvrzeno lékařem: 0 z 15')
      await section(page, 'Pacient')
        .getByRole('button', { name: 'Potvrdit sekci: Pacient' })
        .click()
    }
    // Mock: confirmations are not stored per as_of, so the step-3 confirmation is still there (#122, #172).
    await expect(summary).toContainText('Potvrzeno lékařem: 1 z 15')
    const ps = section(page, 'Stav výkonnosti')
    await ps
      .getByRole('button', { name: 'Ponechat údaj v sekci Stav výkonnosti jako chybějící' })
      .click()
    await expect(ps).toContainText(
      'Ponecháno jako chybějící – potvrdil(a) doc. MUDr. Pavel Hrubý, Ph.D.',
    )
    await page.getByRole('link', { name: 'Připravit MDT' }).first().click()
    await expect(page.getByRole('heading', { name: 'Příprava MDT' })).toBeVisible()
    await expect(page.getByText('Stav k začátku MDT: 21. 10. 2026 8:00')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Nesoulady v dokumentaci' })).toContainText(
      'apixabanu',
    )
    await expect(page.getByRole('region', { name: 'Nesoulady v dokumentaci' })).toContainText(
      'histologii',
    )
    const excluded = page.getByRole('region', { name: 'Po MDT – nezahrnuto' })
    await expect(excluded).toContainText('12_Algeziologie_2026-10-26')
    await expect(excluded).toContainText('13_Psychologie_KOC2_2026-10-27')

    const ready = page.getByRole('region', { name: 'Připravenost k MDT' })
    await ready.getByRole('button', { name: 'Označit jako připravený k MDT' }).click()
    await expect(ready).toContainText('Server vrátil chybějící položky:')
    await ready
      .getByLabel('Důvod prominutí: Stav výkonnosti (PS/ECOG)')
      .fill('Stav výkonnosti v dokumentaci neuveden; doplní ošetřující lékař při jednání.')
    await ready.getByRole('button', { name: 'Prominout a označit jako připravený' }).click()
    await expect(page.getByText('Případ je označen jako připravený k MDT.')).toBeVisible()
    await expect(caseState(page)).toContainText('Připraveno k rozhodnutí/MDT')
  })

  await test.step('5 · MDT handover as of 21. 10. 08:00: record and DOCX', async () => {
    if (!live) await atDate(page, '21. 10. 2026')
    await expect(page.getByText('Stav k začátku MDT: 21. 10. 2026 8:00')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Po MDT – nezahrnuto' })).toContainText(
      '12_Algeziologie_2026-10-26',
    )
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Stáhnout zápis (DOCX)' }).click()
    expect((await download).suggestedFilename()).toMatch(
      new RegExp(`^MDT_zapis_${caseId}_2026-10-21(_NAVRH)?\\.docx$`),
    )
  })

  await test.step('6 · Closing the loop', async () => {
    // Fictitious placeholder text: the runbook pastes data/raw/MDT_zaver.docx; the test needs no clinical content.
    await page.getByLabel('Text závěru MDT').fill(CONCLUSION)
    await page.getByRole('button', { name: 'Zapsat závěr MDT' }).click()
    const signed = page.getByRole('region', { name: 'Podepsaný závěr MDT' })
    await expect(signed).toContainText(CONCLUSION)
    await expect(signed).toContainText('Podepsal(a) doc. MUDr. Pavel Hrubý, Ph.D. · 21. 10. 2026')
    await expect(caseState(page)).toContainText('Závěr KOC/MDT')

    await asRole(page, 'Koordinátorka KOC 2')
    await openCase(page)
    await page.getByRole('link', { name: 'Odeslat závěr' }).click()
    await page.getByRole('button', { name: 'Odeslat závěr PL' }).click()
    await expect(page.getByText('Závěr je předán k doručení praktickému lékaři.')).toBeVisible()
    await expect(caseState(page)).toContainText('Zpětná vazba odeslána')
    if (live) {
      // Proof of delivery in the demo inbox: one notification with a link, no clinical text.
      const inbox = (await (await page.request.get(`${MAILPIT}/api/v1/messages`)).json()) as {
        messages: { ID: string; Subject: string }[]
      }
      expect(inbox.messages.map((m) => m.Subject)).toEqual([
        'Štafeta: zpětná vazba z MDT je k dispozici',
      ])
      const mail = (await (
        await page.request.get(`${MAILPIT}/api/v1/message/${inbox.messages[0].ID}`)
      ).json()) as {
        Text: string
      }
      expect(mail.Text).not.toContain(CONCLUSION)
    }

    await asRole(page, 'Praktický lékař')
    await nav(page, 'Moji pacienti').click()
    await page.getByRole('button', { name: 'Otevřít závěr MDT: Alena Procházková' }).click()
    const opened = page.getByRole('region', { name: 'Závěr MDT k otevření' })
    await expect(opened).toContainText(CONCLUSION)
    await expect(opened).toContainText('Podepsal(a) doc. MUDr. Pavel Hrubý, Ph.D. dne 21. 10. 2026')
    await expect(page.getByText('Otevření závěru bylo zaznamenáno do auditní stopy.')).toBeVisible()

    // A case whose feedback was sent stays in the coordinator's column Aktivní until it is closed (#174); the MDT page
    // is reached from the handover tab (runbook step 6.5).
    await asRole(page, 'Koordinátorka KOC 2')
    await nav(page, 'Fronta případů').click()
    await page
      .getByRole('region', { name: /^Aktivní/ })
      .getByRole('link', { name: 'Alena Procházková' })
      .click()
    await tab(page, 'Handover').click()
    await page.getByRole('link', { name: 'Připravit MDT' }).first().click()
    await expect(page).toHaveURL(new RegExp(`/cases/${caseId}/mdt$`))
    await expect(caseState(page)).toContainText('Zpětná vazba odeslána')
    // The GP opened the conclusion above, so the screen shows when (gp_opened_at) and no read warning (#161).
    await expect(page.getByText('Závěr MDT otevřen praktickým lékařem: 21. 10. 2026', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'Uzavřít případ' }).click()
    await page.getByRole('button', { name: 'Potvrdit uzavření' }).click()
    await expect(page.getByText('Případ je uzavřen.')).toBeVisible()
    await expect(caseState(page)).toContainText('Uzavřeno')
    const clocks = page.getByRole('group', { name: 'Časové intervaly' })
    for (const t of [
      'T1 · první návštěva PL → žádost do KOC',
      'T2 · žádost do KOC → MDT',
      'T3 · MDT → onkologické konzilium',
    ])
      await expect(clocks).toContainText(t)
    // The API computes them (CaseDetail.intervals): the MDT was held, so T2 is measured; the first GP visit and the
    // oncology consult are not recorded (#188, #189). The UI only renders them.
    await expect(clocks).toContainText('19 dní')
    await expect(clocks).toContainText('nezaznamenáno')
    await expect(clocks).toContainText('běží')
  })
})
