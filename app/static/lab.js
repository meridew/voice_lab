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

/** Header with the brand and, on the right, whatever the page passes in (the type switch). */
export function shell(right = '') {
  document.body.insertAdjacentHTML('afterbegin', `
    <header class="mx-auto flex max-w-3xl items-center justify-between px-6 pt-8">
      <div class="text-lg font-semibold tracking-tight text-slate-100">Voice Lab</div>${right}
    </header>`)
  icons()
}

/** Decode any audio file into mono samples plus the sample rate, through one shared decoder (hardware contexts are capped). */
let decoder = null
export async function decodeFile(url) {
  decoder ??= new OfflineAudioContext(1, 1, 48000)
  const data = await decoder.decodeAudioData(await (await fetch(url)).arrayBuffer())
  return { samples: data.getChannelData(0).slice(), sr: data.sampleRate }
}

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
