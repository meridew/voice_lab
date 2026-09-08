// Shared glue for the Voice Lab page: shell, icon helpers, the waveform editor, the library modal, and WAV plumbing.
import WaveSurfer from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/wavesurfer.esm.js'
import RecordPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/plugins/record.esm.js'
import RegionsPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/plugins/regions.esm.js'

export const $ = (id) => document.getElementById(id)
export const fmt = (s) => { const m = Math.floor(s / 60), r = s - m * 60; return `${String(m).padStart(2, '0')}:${r.toFixed(1).padStart(4, '0')}` }
export const icons = () => window.lucide?.createIcons()

export const setButton = (btn, icon, title) => {
  btn.innerHTML = `<i data-lucide="${icon}"></i>`
  btn.title = title
  btn.setAttribute('aria-label', title)
  icons()
}

export const toast = (text) => {
  const el = $('toast')
  el.textContent = text
  clearTimeout(toast.timer)
  toast.timer = setTimeout(() => { el.textContent = '' }, 4000)
}

/** A segmented control (.seg with data-value buttons): `set(value)` selects; user clicks also call onChange(value). */
export function segment(el, onChange) {
  const buttons = [...el.querySelectorAll('button')]
  const set = (value) => buttons.forEach((b) => b.classList.toggle('active', b.dataset.value === value))
  el.onclick = (e) => { const b = e.target.closest('button'); if (b) { set(b.dataset.value); onChange(b.dataset.value) } }
  return { set, get value() { return buttons.find((b) => b.classList.contains('active'))?.dataset.value } }
}

/** Header with the brand and, on the right, whatever the page passes in (the type switch). */
export function shell(right = '') {
  document.body.insertAdjacentHTML('afterbegin', `
    <header class="mx-auto flex max-w-3xl items-center justify-between px-6 pt-8">
      <div class="text-lg font-semibold tracking-tight text-slate-100">Voice Lab</div>${right}
    </header>`)
  icons()
}

/**
 * A modal list built for hundreds of rows. `rows` are { label, meta, facets, pick } where `facets` is a map such as
 * { Type: 'Voice', Stage: 'Original' }: every facet becomes a chip group (any selected value in a group matches;
 * groups combine). Search covers label, meta and facet values. `sorts` are { label, by(a, b) }.
 * Picking closes it, as do Escape and the backdrop.
 */
export function modal(title, rows, { sorts = [] } = {}) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r.facets ?? {})))]
  const values = (key) => [...new Set(rows.map((r) => r.facets?.[key]).filter(Boolean))].sort()
  const state = { q: '', sel: Object.fromEntries(keys.map((k) => [k, new Set()])), sort: 0 }
  const backdrop = document.createElement('div')
  backdrop.className = 'backdrop'
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-label="${title}">
      <header><span class="label">${title}</span><span class="mono text-xs muted" data-count></span>
        <button class="btn-icon" title="Close" aria-label="Close" data-close><i data-lucide="x"></i></button></header>
      <div class="toolbar">
        <input class="input flex-1" placeholder="Search" autocomplete="off" data-q>
        ${sorts.length ? `<select class="select" data-sort>${sorts.map((s, i) => `<option value="${i}">${s.label}</option>`).join('')}</select>` : ''}
      </div>
      ${keys.map((k) => `<div class="chips"><span class="label">${k}</span>${values(k).map((v) =>
        `<button class="chip" data-facet="${k}" data-value="${v}">${v}</button>`).join('')}</div>`).join('')}
      <ul data-list></ul>
    </div>`
  const el = (name) => backdrop.querySelector(`[data-${name}]`)
  const text = (r) => `${r.label} ${r.meta ?? ''} ${Object.values(r.facets ?? {}).join(' ')}`.toLowerCase()
  const render = () => {
    const q = state.q.trim().toLowerCase()
    const list = rows.map((r, i) => ({ r, i })).filter(({ r }) =>
      (!q || text(r).includes(q)) && keys.every((k) => !state.sel[k].size || state.sel[k].has(r.facets?.[k])))
    if (sorts[state.sort]) list.sort((a, b) => sorts[state.sort].by(a.r, b.r))
    el('list').innerHTML = list.map(({ r, i }) =>
      `<li><button class="row" data-row="${i}"><span>${r.label}</span>${Object.values(r.facets ?? {})
        .map((v) => `<span class="tag">${v}</span>`).join('')}<span class="meta mono">${r.meta ?? ''}</span></button></li>`).join('')
      || '<li class="px-3 py-6 text-center text-sm muted">Nothing matches</li>'
    el('count').textContent = `${list.length} of ${rows.length}`
  }
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey) }
  const onKey = (e) => { if (e.key === 'Escape') close() }
  backdrop.onclick = (e) => {
    if (e.target === backdrop || e.target.closest('[data-close]')) return close()
    const chip = e.target.closest('[data-facet]')
    if (chip) {
      const set = state.sel[chip.dataset.facet], v = chip.dataset.value
      set.has(v) ? set.delete(v) : set.add(v)
      chip.classList.toggle('active')
      return render()
    }
    const row = e.target.closest('[data-row]')
    if (row) { close(); rows[+row.dataset.row].pick() }
  }
  el('q').oninput = () => { state.q = el('q').value; render() }
  if (el('sort')) el('sort').onchange = () => { state.sort = +el('sort').value; render() }
  document.addEventListener('keydown', onKey)
  document.body.append(backdrop)
  icons()
  render()
  el('q').focus()
  return close
}

/**
 * The waveform editor used wherever audio is shown: waveform, time readouts, drag-to-select once audio exists,
 * play (the selection when there is one) and crop. With `record: true` it also carries the microphone button;
 * `extra` is HTML for page-specific buttons at the right end of the transport row.
 * Renders into `mount`; returns { ws, load, samples, onReady, hasAudio }.
 */
export function createEditor(mount, { record = false, empty = 'Nothing yet', extra = '' } = {}) {
  mount.innerHTML = `
    <div class="relative">
      <div class="wave" data-wave></div>
      <div class="pointer-events-none absolute inset-0 grid place-items-center text-sm muted" data-empty>${empty}</div>
      <div class="mono mt-2 flex items-baseline justify-between text-xs muted">
        <span data-cur>00:00.0</span><span class="text-sky-300/80" data-sel></span><span data-dur>00:00.0</span>
      </div>
    </div>
    <div class="flex items-center gap-2 pt-5">
      ${record ? '<button class="btn-icon btn-accent" title="Record" aria-label="Record" data-rec><i data-lucide="mic"></i></button>' : ''}
      <button class="btn-icon" title="Play" aria-label="Play" disabled data-play><i data-lucide="play"></i></button>
      <button class="btn-icon" title="Crop to selection" aria-label="Crop to selection" disabled data-crop><i data-lucide="scissors"></i></button>
      ${extra ? `<span class="ml-auto flex gap-2">${extra}</span>` : ''}
    </div>`
  const el = (name) => mount.querySelector(`[data-${name}]`)
  const ws = WaveSurfer.create({
    container: el('wave'), height: 160, normalize: true, dragToSeek: false,
    waveColor: '#334155', progressColor: '#38bdf8', cursorColor: '#e2e8f0', cursorWidth: 1, barWidth: 2, barGap: 1, barRadius: 2,
  })
  const regions = ws.registerPlugin(RegionsPlugin.create())
  const editor = { ws, hasAudio: false }
  const readyHandlers = []
  let region = null, disableDrag = null

  // selection: at most one region, and only once there is audio to select in
  const setSelection = (r) => {
    region = r
    el('sel').textContent = r ? `${fmt(r.start)} – ${fmt(r.end)}` : ''
    el('crop').disabled = !r
  }
  const allowDrag = (on) => {
    if (on && !disableDrag) disableDrag = regions.enableDragSelection({ color: 'rgba(56, 189, 248, .16)' })
    if (!on && disableDrag) { disableDrag(); disableDrag = null }
  }
  regions.on('region-created', (r) => { regions.getRegions().forEach((o) => o !== r && o.remove()); setSelection(r) })
  regions.on('region-updated', (r) => setSelection(r))
  regions.on('region-removed', () => setSelection(null))
  regions.on('region-clicked', (r, e) => { e.stopPropagation(); r.play() })

  ws.on('ready', () => {
    editor.hasAudio = true
    el('empty').hidden = true
    el('dur').textContent = fmt(ws.getDuration())
    el('cur').textContent = fmt(0)
    el('play').disabled = false
    allowDrag(true)
    readyHandlers.forEach((fn) => fn())
  })
  ws.on('timeupdate', (t) => { el('cur').textContent = fmt(t) })
  ws.on('play', () => setButton(el('play'), 'pause', 'Pause'))
  ws.on('pause', () => setButton(el('play'), 'play', 'Play'))
  ws.on('finish', () => setButton(el('play'), 'play', 'Play'))
  el('play').onclick = () => { if (ws.isPlaying()) ws.pause(); else if (region) region.play(); else ws.play() }
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && !el('play').disabled) { e.preventDefault(); el('play').click() }
  })

  editor.samples = (start, end) => monoSamples(ws, start ?? region?.start, end ?? region?.end)
  editor.load = async (src) => { regions.clearRegions(); await (src instanceof Blob ? ws.loadBlob(src) : ws.load(src)) }
  editor.onReady = (fn) => readyHandlers.push(fn)
  el('crop').onclick = async () => {
    if (!region) return
    const { samples, sr } = monoSamples(ws, region.start, region.end)
    await editor.load(wavBlob(samples, sr))
    toast(`Cropped to ${fmt(samples.length / sr)}`)
  }

  if (record) {
    const rec = ws.registerPlugin(RecordPlugin.create({ renderRecordedAudio: true, continuousWaveform: true }))
    let recording = false
    rec.on('record-start', () => {
      recording = true
      regions.clearRegions(); allowDrag(false)
      el('empty').hidden = true
      el('play').disabled = true
      el('rec').innerHTML = '<span class="live inline-block h-3 w-3 rounded-sm bg-red-400"></span>'
      el('rec').title = 'Stop'
      mount.dispatchEvent(new CustomEvent('recording', { detail: true }))
    })
    rec.on('record-progress', (ms) => { el('cur').textContent = fmt(ms / 1000) })
    rec.on('record-end', () => { recording = false; setButton(el('rec'), 'mic', 'Record'); mount.dispatchEvent(new CustomEvent('recording', { detail: false })) })
    el('rec').onclick = async () => {
      if (recording) return rec.stopRecording()
      try { await rec.startRecording() } catch (e) { toast(`Microphone unavailable: ${e.message}`) }
    }
  }
  icons()
  return editor
}

/** The library modal with the lab's metadata as facets. `pick(clip)` receives the chosen clip. */
export function libraryPicker(clips, pick) {
  modal('Library', clips.map((c) => ({
    label: c.label, meta: `${c.when} · ${c.seconds.toFixed(1)} s`, when: c.when, seconds: c.seconds,
    facets: { Type: c.type, Stage: c.kind === 'original' ? 'Original' : 'Augmented', ...(c.voice ? { Voice: c.voice, Mode: c.mode } : {}),
              ...(c.effects ? { Effects: c.effects } : {}) },
    pick: () => pick(c),
  })), { sorts: [
    { label: 'Newest', by: (a, b) => b.when.localeCompare(a.when) },
    { label: 'Oldest', by: (a, b) => a.when.localeCompare(b.when) },
    { label: 'Name', by: (a, b) => a.label.localeCompare(b.label) },
    { label: 'Longest', by: (a, b) => b.seconds - a.seconds },
  ] })
}

/** The editor's right-hand buttons: import a file, open the library. */
export const takeButtons = `
  <button id="btn-import" class="btn-icon" title="Import a file" aria-label="Import a file"><i data-lucide="upload"></i></button>
  <button id="btn-library" class="btn-icon" title="Library" aria-label="Library"><i data-lucide="folder-open"></i></button>
  <input id="file" type="file" accept="audio/*" class="hidden">`

/** Wire import and library to an editor. `fresh()` runs before a new take arrives; `library()` fetches the clips; `pick(clip)` handles a row. */
export function wireTake(editor, { fresh, pick, library }) {
  $('btn-import').onclick = () => $('file').click()
  $('file').onchange = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    fresh()
    await editor.load(file)
    e.target.value = ''
  }
  $('btn-library').onclick = async () => libraryPicker(await library(), pick)
}

/** Decode any audio file into mono samples plus the sample rate, through one shared decoder (hardware contexts are capped). */
let decoder = null
export async function decodeFile(url) {
  decoder ??= new OfflineAudioContext(1, 1, 48000)
  const data = await decoder.decodeAudioData(await (await fetch(url)).arrayBuffer())
  return { samples: data.getChannelData(0).slice(), sr: data.sampleRate }
}

/** Mono samples of the loaded audio between two times (seconds), plus the sample rate. */
export function monoSamples(ws, start, end) {
  const data = ws.getDecodedData(), sr = data.sampleRate
  const mono = new Float32Array(data.length)
  for (let c = 0; c < data.numberOfChannels; c++) {
    const ch = data.getChannelData(c)
    for (let i = 0; i < mono.length; i++) mono[i] += ch[i] / data.numberOfChannels
  }
  return { samples: mono.slice(Math.floor((start ?? 0) * sr), Math.floor((end ?? data.duration) * sr)), sr }
}

/** 16-bit PCM WAV from float samples. */
export function wavBlob(samples, sampleRate) {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf)
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)))
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE'); str(12, 'fmt '); v.setUint32(16, 16, true)
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true)
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, samples.length * 2, true)
  samples.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 32767, true))
  return new Blob([buf], { type: 'audio/wav' })
}

export function download(href, filename) {
  const a = Object.assign(document.createElement('a'), { href, download: filename })
  a.click()
}
