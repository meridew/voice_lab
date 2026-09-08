// Shared helpers for the page: DOM, icons, toasts, the shell and segmented switches, audio plumbing. No imports.
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

/** Header with the brand, the page switch (lab | library), and on the right whatever the page passes in. */
export function shell(page, right = '') {
  const tab = (href, key, icon, title) =>
    `<a class="${page === key ? 'active' : ''}" href="${href}" title="${title}" aria-label="${title}"><i data-lucide="${icon}"></i></a>`
  document.body.insertAdjacentHTML('afterbegin', `
    <header class="mx-auto flex max-w-3xl items-center gap-4 px-6 pt-8">
      <div class="text-lg font-semibold tracking-tight text-slate-100">Voice Lab</div>
      <nav class="seg">${tab('/', 'lab', 'audio-waveform', 'Lab')}${tab('/library.html', 'library', 'list-music', 'Library')}</nav>
      <span class="ml-auto">${right}</span>
    </header>`)
  icons()
}

/** A clip as the lists show it: label, meta, the sort keys, and facets Type, Stage, Voice, Mode, Effects. */
export const clipRow = (c) => ({
  label: c.label, meta: `${c.when} · ${c.seconds.toFixed(1)} s`, when: c.when, seconds: c.seconds,
  facets: { Type: c.type, Stage: { original: 'Original', augmented: 'Augmented', voice: 'Reference' }[c.kind],
            ...(c.voice ? { Voice: c.voice, Mode: c.mode } : {}), ...(c.effects ? { Effects: c.effects } : {}) },
})
export const CLIP_SORTS = [
  { label: 'Newest', by: (a, b) => b.when.localeCompare(a.when) },
  { label: 'Oldest', by: (a, b) => a.when.localeCompare(b.when) },
  { label: 'Name', by: (a, b) => a.label.localeCompare(b.label) },
  { label: 'Longest', by: (a, b) => b.seconds - a.seconds },
]

/** Mono samples of a WaveSurfer's loaded audio between two times (seconds), plus the sample rate. */
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
  Object.assign(document.createElement('a'), { href, download: filename }).click()
}
