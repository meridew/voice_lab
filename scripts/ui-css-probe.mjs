// Print the computed layout of Gradio's outer containers, to see why the app shrinks to content width.
import { createRequire } from 'node:module'
const require = createRequire('C:/Users/danie/vscode-workspace/supreme_perilous/package.json')
const { chromium } = require('playwright')
const browser = await chromium.launch({ channel: 'msedge', headless: true })
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } })
await page.goto('http://localhost:7860', { waitUntil: 'load' })
await page.getByRole('tab', { name: 'Convert' }).waitFor({ timeout: 30000 })
const info = await page.evaluate(() => {
  const pick = (el) => {
    if (!el) return null
    const cs = getComputedStyle(el)
    return { tag: el.tagName, cls: el.className.toString().slice(0, 60), width: el.getBoundingClientRect().width, display: cs.display,
             maxWidth: cs.maxWidth, margin: cs.margin, alignItems: cs.alignItems, flexDirection: cs.flexDirection, position: cs.position }
  }
  const container = document.querySelector('.gradio-container')
  const chain = []
  let el = container
  for (let i = 0; i < 4 && el; i++) { chain.push(pick(el)); el = el.parentElement }
  const app = container?.querySelector('.app') || container?.firstElementChild
  const row = document.querySelector('[role=tabpanel] .row, [role=tabpanel] > div')
  return { container: pick(container), ancestors: chain.slice(1), app: pick(app), tabpanel: pick(document.querySelector('[role=tabpanel]')), firstRow: pick(row) }
})
console.log(JSON.stringify(info, null, 1))
await browser.close()
