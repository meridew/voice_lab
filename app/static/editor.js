// The waveform editor used wherever audio is shown: waveform, time readouts, drag-to-select once audio exists,
// play (the selection when there is one), crop, and optionally the microphone.
import WaveSurfer from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/wavesurfer.esm.js'
import RecordPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/plugins/record.esm.js'
import RegionsPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/plugins/regions.esm.js'
import { fmt, icons, setButton, toast, monoSamples, wavBlob } from './lab.js'

/**
 * Renders into `mount`; `extra` is HTML for page-specific buttons at the right end of the transport row.
 * Returns { ws, load, samples, onReady, hasAudio }. With `record: true`, `mount` gets a 'recording' event (detail true/false).
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
