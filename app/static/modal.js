// Overlays: a filterable list (the library picker, the effects) and a small form dialog (a new voice, the microphone).
import { icons } from './lab.js'
import { filterList, tags } from './list.js'

const open = (title, body, extraClass = '') => {
  const backdrop = document.createElement('div')
  backdrop.className = 'backdrop'
  backdrop.innerHTML = `
    <div class="modal ${extraClass}" role="dialog" aria-label="${title}">
      <header><span class="label">${title}</span>
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
 * A modal list in a frame that never changes size: `rows` are { label, meta?, facets?, pick, remove? } (filterList does
 * the filtering). Picking closes it, as do Escape and the backdrop; a row with `remove` gets a bin that removes it in place.
 */
export function modal(title, rows, { sorts = [] } = {}) {
  const { backdrop, close, el } = open(title, '<div class="frame" data-body></div>')
  const list = filterList(el('body'), rows, { sorts, row: (r, i) => `<li class="flex items-center gap-1">
      <button class="row" data-row="${i}"><span>${r.label}</span>${tags(r)}<span class="meta mono">${r.meta ?? ''}</span></button>
      ${r.remove ? `<button class="btn-icon btn-sm" title="Delete" aria-label="Delete" data-remove="${i}"><i data-lucide="trash-2"></i></button>` : ''}
    </li>` })
  backdrop.onclick = async (e) => {
    if (e.target === backdrop || e.target.closest('[data-close]')) return close()
    const bin = e.target.closest('[data-remove]')
    if (bin) { const i = +bin.dataset.remove; await rows[i].remove(); rows.splice(i, 1); return list.render() }
    const row = e.target.closest('[data-row]')
    if (row) { close(); rows[+row.dataset.row].pick() }
  }
  list.focus()
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
