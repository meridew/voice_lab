// A filterable list, used by the lab's picker modal and by the library page: one row of controls (search, a select per
// facet that has more than one value, sort, count) over rows drawn by the caller.
import { icons } from './lab.js'

/**
 * Renders into `mount` and returns { render, focus }. `rows` are { label, meta?, text?, facets? } plus whatever the
 * caller's `row(r, i)` needs: it returns one <li>, with i the row's index in `rows` for click delegation. Search covers
 * label, meta, text and facet values; `sorts` are { label, by(a, b) }. To drop a row, splice `rows` and call render().
 */
export function filterList(mount, rows, { sorts = [], row, empty = 'Nothing matches' }) {
  const values = (key) => [...new Set(rows.map((r) => r.facets?.[key]).filter(Boolean))].sort()
  const facets = [...new Set(rows.flatMap((r) => Object.keys(r.facets ?? {})))].filter((k) => values(k).length > 1)
  const state = { q: '', sel: Object.fromEntries(facets.map((k) => [k, ''])), sort: 0 }
  mount.innerHTML = `
    <div class="toolbar">
      <input class="input" placeholder="Search" autocomplete="off" data-q>
      ${facets.map((k) => `<select class="select" title="${k}" data-facet="${k}"><option value="">${k}</option>${values(k).map((v) => `<option>${v}</option>`).join('')}</select>`).join('')}
      ${sorts.length ? `<select class="select" title="Sort" data-sort>${sorts.map((s, i) => `<option value="${i}">${s.label}</option>`).join('')}</select>` : ''}
      <span class="mono text-xs muted" data-count></span>
    </div>
    <ul class="list" data-list></ul>`
  const el = (name) => mount.querySelector(`[data-${name}]`)
  const text = (r) => `${r.label} ${r.meta ?? ''} ${r.text ?? ''} ${Object.values(r.facets ?? {}).join(' ')}`.toLowerCase()
  const render = () => {
    const q = state.q.trim().toLowerCase()
    const list = rows.map((r, i) => ({ r, i })).filter(({ r }) =>
      (!q || text(r).includes(q)) && facets.every((k) => !state.sel[k] || r.facets?.[k] === state.sel[k]))
    if (sorts[state.sort]) list.sort((a, b) => sorts[state.sort].by(a.r, b.r))
    el('list').innerHTML = list.map(({ r, i }) => row(r, i)).join('') || `<li class="px-3 py-6 text-center text-sm muted">${empty}</li>`
    el('count').textContent = `${list.length} of ${rows.length}`
    icons()
  }
  mount.querySelectorAll('[data-facet]').forEach((s) => { s.onchange = () => { state.sel[s.dataset.facet] = s.value; render() } })
  el('q').oninput = () => { state.q = el('q').value; render() }
  if (el('sort')) el('sort').onchange = () => { state.sort = +el('sort').value; render() }
  render()
  return { render, focus: () => el('q').focus() }
}
