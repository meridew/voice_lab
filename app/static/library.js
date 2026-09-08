// The library page: every original, augmented clip and reference voice, filtered like the lab's picker. Each row plays,
// renames (click the name), flips Voice and SFX (click the tag), exports for the game or for sharing, and deletes.
import { $, toast, shell, clipRow, CLIP_SORTS } from './lab.js'
import { filterList } from './list.js'
import { api } from './api.js'

shell('library')
const fail = (e) => { console.error(e); toast(`Failed: ${e.message}`) }
const lib = await api.library()
const rows = [...lib.clips, ...lib.voices].map(clipRow)
const editable = (r) => r.clip.kind !== 'voice'          // a voice is named by its file and is always a Voice

// ---- playback: one player; the row that is playing shows pause
const player = new Audio()
let playingRow = null
player.onpause = player.onended = () => { if (player.paused && playingRow) { playingRow = null; list.render() } }
const play = async (r) => {
  if (r === playingRow) return player.pause()
  player.src = r.clip.url
  await player.play()
  playingRow = r
  list.render()
}

// ---- the rows: play, the name, the Type tag, meta, then actions that show under the pointer
const list = filterList($('library'), rows, { sorts: CLIP_SORTS, row: (r, i) => {
  const [icon, title] = r === playingRow ? ['pause', 'Pause'] : ['play', 'Play']
  return `<li class="line">
    <button class="btn-icon btn-sm" title="${title}" aria-label="${title}" data-play="${i}"><i data-lucide="${icon}"></i></button>
    <span class="name" ${editable(r) ? `data-name="${i}" title="Rename"` : ''}>${r.label}</span>
    ${editable(r) ? `<button class="tag" title="Voice or SFX" data-type="${i}">${r.clip.type}</button>` : `<span class="tag">${r.tag}</span>`}
    <span class="meta mono" title="${r.title}">${r.meta}</span>
    <a class="btn-icon btn-sm" title="Export for the game (Opus)" aria-label="Export for the game" href="${api.exportUrl(r.clip, 'opus')}" download><i data-lucide="gamepad-2"></i></a>
    <a class="btn-icon btn-sm" title="Share (MP3)" aria-label="Share" href="${api.exportUrl(r.clip, 'mp3')}" download><i data-lucide="share-2"></i></a>
    <button class="btn-icon btn-sm" title="Delete" aria-label="Delete" data-remove="${i}"><i data-lucide="trash-2"></i></button>
  </li>`
} })

const update = async (r, fields) => {
  try { Object.assign(r, clipRow(await api.updateClip(r.clip, fields))) } catch (e) { fail(e) }
  list.render()
}
const rename = (r, span) => {                            // the name becomes a field: Enter or leaving saves, Escape cancels
  const input = Object.assign(document.createElement('input'), { className: 'input rename', value: r.label })
  span.replaceChildren(input)
  input.focus()
  input.select()
  let done = false
  const finish = (save) => {
    if (done) return
    done = true
    const label = input.value.trim()
    if (save && label && label !== r.label) update(r, { label }); else list.render()
  }
  input.onkeydown = (e) => { if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false) }
  input.onblur = () => finish(true)
}
$('library').addEventListener('click', async (e) => {
  const hit = (attr) => e.target.closest(`[data-${attr}]`)
  const at = (btn, attr) => rows[+btn.dataset[attr]]
  const playBtn = hit('play'), typeBtn = hit('type'), nameEl = hit('name'), bin = hit('remove')
  if (playBtn) return play(at(playBtn, 'play')).catch(fail)
  if (typeBtn) return update(at(typeBtn, 'type'), { type: at(typeBtn, 'type').clip.type === 'Voice' ? 'SFX' : 'Voice' })
  if (nameEl && !nameEl.querySelector('input')) return rename(at(nameEl, 'name'), nameEl)
  if (bin) {
    const r = at(bin, 'remove')
    if (r === playingRow) player.pause()
    try { await api.deleteClip(r.clip); rows.splice(rows.indexOf(r), 1); list.render(); toast(`Deleted ${r.label}`) } catch (e) { fail(e) }
  }
})
