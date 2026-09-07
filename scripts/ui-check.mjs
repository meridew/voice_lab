// Headless browser check of the Effects chain panel using the installed Edge via Playwright.
//   node scripts/ui-check.mjs   (server running on http://localhost:7860)
import { createRequire } from 'node:module'
const require = createRequire('C:/Users/danie/vscode-workspace/supreme_perilous/package.json')
const { chromium } = require('playwright')

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
for (let attempt = 0; ; attempt++) {                                // the server may still be starting
  try { await page.goto('http://localhost:7860', { waitUntil: 'load' }); break }   // Gradio keeps a heartbeat open, so never "networkidle"
  catch (e) { if (attempt >= 20) throw e; await new Promise((r) => setTimeout(r, 3000)) }
}
await page.getByRole('tab', { name: 'Effects' }).waitFor({ timeout: 30000 })
await page.screenshot({ path: 'C:/Users/danie/vscode-workspace/voice-lab/logs/ui-convert.png', fullPage: false })
await page.getByRole('tab', { name: 'Effects' }).click()
await page.getByRole('button', { name: 'Add', exact: true }).click()
await page.getByText('1. Pitch shift').waitFor({ timeout: 20000 })
const ranges = await page.locator('[role=tabpanel]:visible input[type=range]').count()
await page.getByRole('button', { name: 'Add', exact: true }).click()
await page.getByText('2. Pitch shift').waitFor({ timeout: 20000 })
// change the first slider and check the JSON view follows
const slider = page.locator('[role=tabpanel]:visible input[type=range]').first()
await slider.fill('4')
await slider.dispatchEvent('change')
await page.waitForTimeout(1500)
await page.getByText('Chain as JSON').click()
await page.waitForTimeout(800)
const json = await page.locator('[role=tabpanel]:visible').innerText()
const jsonOk = json.includes('"semitones": 4') || json.includes('"semitones":4')
await page.getByRole('button', { name: '✕' }).last().click()
await page.waitForTimeout(1500)
const stepsAfterRemove = await page.locator('[role=tabpanel]:visible').innerText().then((t) => (t.match(/\d+\. Pitch shift/g) || []).length)
await page.getByText('Chain as JSON').click()   // collapse again for the screenshot
await page.waitForTimeout(500)
await page.screenshot({ path: 'C:/Users/danie/vscode-workspace/voice-lab/logs/ui-effects.png', fullPage: false })
await page.getByRole('tab', { name: 'Library' }).click()
await page.waitForTimeout(800)
await page.screenshot({ path: 'C:/Users/danie/vscode-workspace/voice-lab/logs/ui-library.png', fullPage: false })
console.log(JSON.stringify({ rangesAfterFirstAdd: ranges, sliderEditReflectedInJson: jsonOk, stepsAfterRemove, errors }, null, 1))
await browser.close()
