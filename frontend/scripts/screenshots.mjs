// Captures the PR screenshots against a running dev server (mocks on). Usage: node scripts/screenshots.mjs
import { chromium } from '@playwright/test'

const base = process.env.BASE_URL ?? 'http://localhost:5173'
const A = '/cases/rakathon-2026-prochazkova'
const shots = [
  ['inbox', '/inbox', { role: 'coordinator', today: '2026-10-02' }],
  ['case-detail', A, { role: 'coordinator', today: '2026-10-21' }],
  ['handover', `${A}/handover`, { role: 'physician', today: '2026-10-21' }],
  ['mdt', `${A}/mdt`, { role: 'physician', today: '2026-10-21' }],
  ['referral', '/referral/new', { role: 'gp', today: '2026-10-02' }],
  ['gp', '/gp', { role: 'gp', today: '2026-10-22' }],
  ['reviewer', '/reviewer', { role: 'reviewer', today: '2026-10-21' }],
]

const browser = await chromium.launch()
for (const [name, path, demo] of shots) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'cs-CZ', timezoneId: 'Europe/Prague' })
  await ctx.addInitScript((d) => localStorage.setItem('stafeta.demo', JSON.stringify(d)), demo)
  const page = await ctx.newPage()
  const errors = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  await page.goto(base + path)
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(400)
  await page.screenshot({ path: `docs/screenshots/${name}.png`, fullPage: name === 'handover' || name === 'mdt' })
  console.log(name, errors.length ? `console errors: ${errors.join(' | ')}` : 'ok')
  await ctx.close()
}
await browser.close()
