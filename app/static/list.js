// A filterable list, used by the lab's picker modal and by the library page: search, a chip group per facet, sorts, a count.
import { icons } from './lab.js'

/** The facet values of a row as tags, skipping any keys the caller draws itself. */
export const tags = (r, skip = []) =>
  Object.entries(r.facets ?? {}).filter(([k]) => !skip.includes(k)).map(([, v]) => `<span class="tag">${v}</span>`).join('')

/**
 * Renders into `mount` and returns { render, focus }. `rows` are { label, meta?, facets? } plus whatever the caller's
 * `row(r, i)` needs: it returns one <li>, with i the row's index in `rows` for click delegation. Every facet key becomes
 * a chip group (any selected value in a group matches; groups combine); search covers label, meta and facet values;
 * `sorts` are { label, by(a, b) }. To drop a row, splice `rows` and call render().
 */
export function filterList(mount, rows, { sorts = [], row, empty = 'Nothing matches' }) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r.facets ?? {})))]
  const values = (key) => [...new Set(rows.map((r) => r.facets?.[key]).filter(Boolean))].sort()
  const state = { q: '', sel: Object.fromEntries(keys.map((k) => [k, new Set()])), sort: 0 }
  mount.innerHTML = `
    <div class="toolbar">
      <input class="input flex-1" placeholder="Search" autocomplete="off" data-q>
      ${sorts.length ? `<select class="select" data-sort>${sorts.map((s, i) => `<option value="${i}">${s.label}</option>`).join('')}</select>` : ''}
      <span class="mono text-xs muted" data-count></span>
    </div>
    ${keys.map((k) => `<div class="chips"><span class="label">${k}</span>${values(k).map((v) =>
      `<button class="chip" data-facet="${k}" data-value="${v}">${v}</button>`).join('')}</div>`).join('')}
    <ul class="list" data-list></ul>`
  const el = (name) => mount.querySelector(`[data-${name}]`)
  const text = (r) => `${r.label} ${r.meta ?? ''} ${Object.values(r.facets ?? {}).join(' ')}`.toLowerCase()
  const render = () => {
    const q = state.q.trim().toLowerCase()
    const list = rows.map((r, i) => ({ r, i })).filter(({ r }) =>
      (!q || text(r).includes(q)) && keys.every((k) => !state.sel[k].size || state.sel[k].has(r.facets?.[k])))
    if (sorts[state.sort]) list.sort((a, b) => sorts[state.sort].by(a.r, b.r))
    el('list').innerHTML = list.map(({ r, i }) => row(r, i)).join('') || `<li class="px-3 py-6 text-center text-sm muted">${empty}</li>`
    el('count').textContent = `${list.length} of ${rows.length}`
    icons()
  }
  mount.addEventListener('click', (e) => {
    const chip = e.target.closest('[data-facet]')
    if (!chip) return
    const set = state.sel[chip.dataset.facet], v = chip.dataset.value
    set.has(v) ? set.delete(v) : set.add(v)
    chip.classList.toggle('active')
    render()
  })
  el('q').oninput = () => { state.q = el('q').value; render() }
  if (el('sort')) el('sort').onchange = () => { state.sort = +el('sort').value; render() }
  render()
  return { render, focus: () => el('q').focus() }
}
