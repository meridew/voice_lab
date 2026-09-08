// The waveform editor used wherever audio is shown: waveform, time readouts, drag-to-select once audio exists,
// play (the selection when there is one), crop, and optionally the microphone.
import WaveSurfer from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/wavesurfer.esm.js'
import RegionsPlugin from 'https://cdn.jsdelivr.net/npm/wavesurfer.js@7/dist/plugins/regions.esm.js'
import { fmt, icons, setButton, toast, monoSamples, wavBlob } from './lab.js'

// A dry, unprocessed microphone: the browser's call-oriented defaults (echo cancellation, noise suppression, automatic
// gain) thin a voice out, and the default Opus bitrate is low; 128 kbps at 48 kHz is transparent for speech.
const MIC = { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } }
const ENCODE = { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 128000 }

/**
 * Renders into `mount`; `extra` is HTML for page-specific buttons at the right end of the transport row.
 * Returns { ws, load, samples, onReady, hasAudio }; onReady's callback gets `edited`, true when the reload was a crop or reverse
 * made here. With `record: true`, `mount` gets a 'recording' event (detail true/false).
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
      <button class="btn-icon" title="Reverse" aria-label="Reverse" disabled data-reverse><i data-lucide="flip-horizontal"></i></button>
      ${extra ? `<span class="ml-auto flex gap-2">${extra}</span>` : ''}
    </div>`
  const el = (name) => mount.querySelector(`[data-${name}]`)
  // sampleRate is the decoder's rate, 8 kHz by default because WaveSurfer only draws with it. Here the decoded data is also
  // the audio that gets cropped, converted and rendered, so it decodes at the rate the microphone and the exports use.
  const ws = WaveSurfer.create({
    container: el('wave'), height: 160, normalize: true, dragToSeek: false, sampleRate: 48000,
    waveColor: '#334155', progressColor: '#38bdf8', cursorColor: '#e2e8f0', cursorWidth: 1, barWidth: 2, barGap: 1, barRadius: 2,
  })
  const regions = ws.registerPlugin(RegionsPlugin.create())
  const editor = { ws, hasAudio: false }
  const readyHandlers = []
  let region = null, disableDrag = null, edited = false

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
    el('play').disabled = el('reverse').disabled = false
    allowDrag(true)
    readyHandlers.forEach((fn) => fn(edited))
    edited = false
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
  const edit = async (samples, sr) => { edited = true; await editor.load(wavBlob(samples, sr)) }   // a reload the page should keep
  el('crop').onclick = async () => {
    if (!region) return
    const { samples, sr } = monoSamples(ws, region.start, region.end)
    await edit(samples, sr)
    toast(`Cropped to ${fmt(samples.length / sr)}`)
  }
  el('reverse').onclick = async () => {
    const { samples, sr } = monoSamples(ws)
    await edit(samples.reverse(), sr)
  }

  if (record) {
    // Recorded with MediaRecorder directly and loaded as the real audio: WaveSurfer's record plugin hands over its
    // low-resolution live-waveform peaks as the decoded data, which is what an earlier version saved.
    let recorder = null, chunks = [], timer = null
    el('rec').onclick = async () => {
      if (recorder) return recorder.stop()
      let stream
      try { stream = await navigator.mediaDevices.getUserMedia(MIC) } catch (e) { return toast(`Microphone unavailable: ${e.message}`) }
      chunks = []
      recorder = new MediaRecorder(stream, MediaRecorder.isTypeSupported(ENCODE.mimeType) ? ENCODE : { audioBitsPerSecond: ENCODE.audioBitsPerSecond })
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        clearInterval(timer)
        const blob = new Blob(chunks, { type: recorder.mimeType })
        recorder = null
        setButton(el('rec'), 'mic', 'Record')
        el('empty').textContent = empty
        mount.dispatchEvent(new CustomEvent('recording', { detail: false }))
        await editor.load(blob)
      }
      regions.clearRegions(); allowDrag(false)
      el('play').disabled = el('reverse').disabled = true
      el('empty').textContent = 'Recording'; el('empty').hidden = false
      el('rec').innerHTML = '<span class="live inline-block h-3 w-3 rounded-sm bg-red-400"></span>'
      el('rec').title = 'Stop'
      const t0 = performance.now()
      timer = setInterval(() => { el('cur').textContent = fmt((performance.now() - t0) / 1000) }, 100)
      recorder.start()
      mount.dispatchEvent(new CustomEvent('recording', { detail: true }))
    }
  }
  icons()
  return editor
}
