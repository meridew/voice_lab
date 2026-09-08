// Overlays: a filterable list (the library, the effects) and a small form dialog (a new voice).
import { icons } from './lab.js'

const open = (title, body, extraClass = '') => {
  const backdrop = document.createElement('div')
  backdrop.className = 'backdrop'
  backdrop.innerHTML = `
    <div class="modal ${extraClass}" role="dialog" aria-label="${title}">
      <header><span class="label">${title}</span><span class="mono text-xs muted" data-count></span>
        <button class="btn-icon" title="Close" aria-label="Close" type="button" data-close><i data-lucide="x"></i></button></header>
      ${body}
    </div>`
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey) }
  const onKey = (e) => { if (e.key === 'Escape') close() }
  document.addEventListener('keydown', onKey)
  document.body.append(backdrop)
  icons()
  return { backdrop, close, el: (name) => backdrop.querySelector(`[data-${name}]`) }
}

/**
 * A modal list built for hundreds of rows. `rows` are { label, meta, facets, pick, remove? } where `facets` is a
 * map such as { Type: 'Voice', Stage: 'Original' }: every facet becomes a chip group (any selected value in a group
 * matches; groups combine). Search covers label, meta and facet values. `sorts` are { label, by(a, b) }. Picking
 * closes it, as do Escape and the backdrop; a row with `remove` gets a bin icon that removes it in place.
 */
export function modal(title, rows, { sorts = [] } = {}) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r.facets ?? {})))]
  const values = (key) => [...new Set(rows.map((r) => r.facets?.[key]).filter(Boolean))].sort()
  const state = { q: '', sel: Object.fromEntries(keys.map((k) => [k, new Set()])), sort: 0 }
  const { backdrop, close, el } = open(title, `
      <div class="toolbar">
        <input class="input flex-1" placeholder="Search" autocomplete="off" data-q>
        ${sorts.length ? `<select class="select" data-sort>${sorts.map((s, i) => `<option value="${i}">${s.label}</option>`).join('')}</select>` : ''}
      </div>
      ${keys.map((k) => `<div class="chips"><span class="label">${k}</span>${values(k).map((v) =>
        `<button class="chip" data-facet="${k}" data-value="${v}">${v}</button>`).join('')}</div>`).join('')}
      <ul data-list></ul>`)
  const text = (r) => `${r.label} ${r.meta ?? ''} ${Object.values(r.facets ?? {}).join(' ')}`.toLowerCase()
  const render = () => {
    const q = state.q.trim().toLowerCase()
    const list = rows.map((r, i) => ({ r, i })).filter(({ r }) =>
      (!q || text(r).includes(q)) && keys.every((k) => !state.sel[k].size || state.sel[k].has(r.facets?.[k])))
    if (sorts[state.sort]) list.sort((a, b) => sorts[state.sort].by(a.r, b.r))
    el('list').innerHTML = list.map(({ r, i }) => `<li class="flex items-center gap-1">
        <button class="row" data-row="${i}"><span>${r.label}</span>${Object.values(r.facets ?? {}).map((v) => `<span class="tag">${v}</span>`).join('')}
          <span class="meta mono">${r.meta ?? ''}</span></button>
        ${r.remove ? `<button class="btn-icon btn-sm" title="Delete" aria-label="Delete" data-remove="${i}"><i data-lucide="trash-2"></i></button>` : ''}
      </li>`).join('') || '<li class="px-3 py-6 text-center text-sm muted">Nothing matches</li>'
    el('count').textContent = `${list.length} of ${rows.length}`
    icons()
  }
  backdrop.onclick = async (e) => {
    if (e.target === backdrop || e.target.closest('[data-close]')) return close()
    const chip = e.target.closest('[data-facet]')
    if (chip) {
      const set = state.sel[chip.dataset.facet], v = chip.dataset.value
      set.has(v) ? set.delete(v) : set.add(v)
      chip.classList.toggle('active')
      return render()
    }
    const bin = e.target.closest('[data-remove]')
    if (bin) { const i = +bin.dataset.remove; await rows[i].remove(); rows.splice(i, 1); return render() }
    const row = e.target.closest('[data-row]')
    if (row) { close(); rows[+row.dataset.row].pick() }
  }
  el('q').oninput = () => { state.q = el('q').value; render() }
  if (el('sort')) el('sort').onchange = () => { state.sort = +el('sort').value; render() }
  render()
  el('q').focus()
  return close
}

/** A small form. `body` is the fields' HTML; `onSubmit(formData)` runs on the tick and the dialog closes if it resolves. */
export function dialog(title, body, onSubmit) {
  const { backdrop, close, el } = open(title, `
      <form data-form>${body}
        <footer><button class="btn-icon btn-accent" title="Save" aria-label="Save" type="submit"><i data-lucide="check"></i></button></footer>
      </form>`, 'dialog')
  backdrop.onclick = (e) => { if (e.target === backdrop || e.target.closest('[data-close]')) close() }
  el('form').onsubmit = async (e) => {
    e.preventDefault()
    const button = e.target.querySelector('[type=submit]')
    button.disabled = true
    try { await onSubmit(new FormData(e.target)); close() } finally { button.disabled = false }
  }
  el('form').querySelector('input, select, textarea')?.focus()
  return close
}
