// The page. One waveform holds a history of take, conversion and render; everything else reads or feeds it.
import { $, icons, setButton, toast, shell, segment, wavBlob, download, clipRow, CLIP_SORTS } from './lab.js'
import { modal, dialog } from './modal.js'
import { createEditor } from './editor.js'
import { EFFECTS, newStep, chainName, chainRate, connectChain, renderChain, cardHtml } from './effects.js'
import { api } from './api.js'

shell('lab', `<div id="type" class="seg">
         <button data-value="Voice" class="active" title="A voice line"><i data-lucide="mic-vocal"></i>Voice</button>
         <button data-value="SFX" title="A sound effect"><i data-lucide="drum"></i>SFX</button>
       </div>`)

// ---- state
let lib = { voices: [], clips: [], rates: {}, warm: {}, kokoro: {} }
const history = []                                    // { label, clip?, rendered?, samples, sr }: the samples arrive when the waveform shows the entry
const chain = []                                      // { id, type, params, on, node }
let nextId = 1, ctx = null, source = null
const top = () => history[history.length - 1]
const takeName = () => $('name').value.trim()
const fail = (e) => { console.error(e); toast(`Failed: ${e.message}`) }
const clipRef = (t) => (t?.clip ? `${t.clip.kind}:${t.clip.name}` : '')
const DEFAULT_LINE = 'Docking clearance granted. Hold your approach vector and cut thrust at two hundred metres. Welcome to Meridian Port.'

// ---- the switches: type tags what gets saved and hides the voice parts for SFX; mode picks the model
const showVoiceParts = () => { $('voice-row').hidden = $('convert').hidden = type.value !== 'Voice' }
const type = segment($('type'), () => { showVoiceParts(); refresh() })
const mode = segment($('mode'), () => { $('pitch-row').hidden = mode.value !== 'v1'; refresh() })

// ---- voices
const loadLibrary = async () => {
  lib = await api.library()
  const current = $('voice').value
  $('voice').innerHTML = lib.voices.map((v) => `<option value="${v.name}">${v.name} · ${v.seconds.toFixed(1)} s</option>`).join('')
  if (lib.voices.some((v) => v.name === current)) $('voice').value = current
  return lib
}
const voice = () => lib.voices.find((v) => v.name === $('voice').value)
const audition = new Audio()
audition.onended = audition.onpause = () => setButton($('play-voice'), 'play', 'Play')
$('play-voice').onclick = () => {
  if (!audition.paused) return audition.pause()
  if (!voice()) return
  audition.src = voice().url; audition.play(); setButton($('play-voice'), 'pause', 'Pause')
}
$('voice').onchange = () => refresh()                  // the estimate depends on the reference's length
$('btn-voice-new').onclick = () => dialog('New voice', `
    <label><span class="label">Name</span><input class="input" name="name" required autocomplete="off"></label>
    <label><span class="label">Kokoro voice</span><select class="select" name="kokoro">
      ${Object.entries(lib.kokoro).map(([group, names]) => `<optgroup label="${group}">${names.map((n) => `<option>${n}</option>`).join('')}</optgroup>`).join('')}
    </select></label>
    <label><span class="label">Text</span><textarea class="input" name="text" rows="3">${DEFAULT_LINE}</textarea></label>
    <label><span class="label">Speed</span><input type="range" name="speed" min="0.6" max="1.4" step="0.05" value="0.9"></label>`,
  async (form) => {
    const made = await api.createVoice(Object.fromEntries(form))
    await loadLibrary()
    $('voice').value = made.name
    toast(`Made voice ${made.name}`)
    refresh()
  })

// ---- the waveform
const editor = createEditor($('editor'), {
  record: true, empty: 'Record, import, or open the library',
  extra: `<button id="btn-import" class="btn-icon" title="Import a file" aria-label="Import a file"><i data-lucide="upload"></i></button>
          <button id="btn-library" class="btn-icon" title="Library" aria-label="Library"><i data-lucide="folder-open"></i></button>
          <input id="file" type="file" accept="audio/*" class="hidden">`,
})
const estimateSeconds = () => {                        // the server's fit, from the rates it serves
  const r = lib.rates[mode.value], t = top(), steps = +$('steps').value
  return r && t?.samples ? r.fixed + r.per_step_second * steps * (t.samples.length / t.sr + (voice()?.seconds ?? 10)) + (lib.warm[mode.value] ? 0 : r.cold) : 0
}
const refresh = () => {
  const t = top()
  $('btn-go').disabled = !t?.samples || t.rendered || !lib.voices.length
  $('btn-render').disabled = !t?.samples || !chain.some((i) => i.on)
  $('btn-undo').disabled = history.length < 2
  $('btn-game').disabled = $('btn-share').disabled = !t?.clip || history.length < 2
  $('est').textContent = t && !t.rendered && type.value === 'Voice' ? `~${(estimateSeconds() / 60).toFixed(1)} min` : ''
  wire()
}
let takeNext = false                                  // the next 'ready' is a fresh take (a recording or an import) to save
editor.onReady(async (edited) => {
  const isTake = takeNext
  takeNext = false                                    // decided before any await, so a second 'ready' cannot save the take twice
  if (isTake) {
    history.length = 0
    const entry = { ...editor.samples(), label: takeName() || 'take' }
    history.push(entry)
    try {
      entry.clip = await api.saveOriginal(wavBlob(entry.samples, entry.sr), takeName(), type.value, recorded ? editor.mic : null)
      entry.label = entry.clip.label
      toast(`Saved original ${entry.clip.label} · ${type.value}`)
    } catch (e) { fail(e) }
  } else if (top()) {                                 // an entry shown from its file takes its samples here; a crop or reverse replaces them
    const t = top()
    if (edited || !t.samples) Object.assign(t, editor.samples())
    if (edited && t.clip?.kind === 'original') api.updateOriginal(t.clip.name, wavBlob(t.samples, t.sr)).catch(fail)
  }
  refresh()
})
let recorded = false                                  // whether the pending take came from the microphone (its settings go in the sidecar)
const fresh = (fromMic) => { takeNext = true; recorded = fromMic }
const load = (entry) => editor.load(entry.clip?.url ?? wavBlob(entry.samples, entry.sr))
const show = async (entry) => { history.push(entry); await load(entry) }
$('editor').addEventListener('recording', (e) => { if (e.detail) { fresh(true); history.length = 0; refresh() } })
$('btn-import').onclick = () => $('file').click()
$('file').onchange = async (e) => {
  const file = e.target.files[0]
  if (!file) return
  if (!takeName()) $('name').value = file.name.replace(/\.[^.]+$/, '')
  fresh(false)
  await editor.load(file)
  e.target.value = ''
}

// ---- the library: pick a clip into the waveform, or delete one
const pick = async (c) => {
  $('name').value = c.label
  if (c.type) { type.set(c.type); showVoiceParts() }
  history.length = 0
  if (c.kind === 'augmented' && c.input) {            // its original, when it is still in the library, sits behind the undo
    const [kind, name] = c.input.split(':')
    const o = lib.clips.find((x) => x.kind === kind && x.name === name)
    if (o) history.push({ label: o.label, clip: o })
  }
  await show({ label: c.label, clip: c, rendered: !!c.effects })
}
const remove = async (c) => {
  await api.deleteClip(c)
  history.forEach((t) => { if (t.clip?.kind === c.kind && t.clip?.name === c.name) delete t.clip })
  history.splice(0, history.length, ...history.filter((t) => t.samples || t.clip))   // an entry only its file held goes with it
  refresh()
}
$('btn-library').onclick = async () => modal('Library', (await loadLibrary()).clips.map((c) => ({ ...clipRow(c), pick: () => pick(c), remove: () => remove(c) })),
                                                        { sorts: CLIP_SORTS })

// ---- live chain on playback: media element → active effects → speakers (dry when the top entry is a render)
const live = () => {
  if (!ctx) { ctx = new AudioContext(); source = ctx.createMediaElementSource(editor.ws.getMediaElement()) }
  return ctx
}
editor.ws.on('play', () => { live().resume(); wire() })
const wire = () => {
  if (!ctx) return
  source.disconnect()
  chain.forEach((i) => i.node?.output.disconnect())
  const dry = !!top()?.rendered
  connectChain(ctx, dry ? [] : chain, source, ctx.destination, true)
  editor.ws.setPlaybackRate(dry ? 1 : chainRate(chain), false)
}

// ---- chain cards: slider moves update the node in place; structural changes re-render the cards
const renderChainCards = () => {
  $('chain-empty').hidden = chain.length > 0
  $('chain').innerHTML = chain.map(cardHtml).join('')
  icons()
  refresh()
}
$('chain').oninput = (e) => {
  const card = e.target.closest('[data-card]'), key = e.target.dataset.param
  if (!card || !key) return
  const i = chain.find((x) => x.id === +card.dataset.card), p = EFFECTS[i.type].params.find((x) => x.key === key)
  i.params[key] = +e.target.value
  card.querySelector(`[data-value="${key}"]`).textContent = p.fmt(i.params[key])
  if (EFFECTS[i.type].rate) wire(); else i.node?.set(i.params)
}
$('chain').onclick = (e) => {
  const card = e.target.closest('[data-card]'); if (!card) return
  const idx = chain.findIndex((x) => x.id === +card.dataset.card)
  if (e.target.closest('[data-toggle]')) chain[idx].on = !chain[idx].on
  else if (e.target.closest('[data-remove]')) chain.splice(idx, 1)
  else if (e.target.closest('[data-up]') && idx > 0) [chain[idx - 1], chain[idx]] = [chain[idx], chain[idx - 1]]
  else return
  renderChainCards()
}
$('btn-add').onclick = () => modal('Effects', Object.entries(EFFECTS).map(([key, e]) => ({
  label: e.label, tag: e.category, facets: { Category: e.category },
  pick: () => { chain.push(newStep(key, nextId++)); live(); renderChainCards() },
})))

// ---- convert (voice): the server runs the model; the bar follows its estimate; the result replaces the take
$('steps').oninput = () => { $('steps-v').textContent = $('steps').value; refresh() }
$('pitch').oninput = () => { const v = +$('pitch').value; $('pitch-v').textContent = `${v >= 0 ? '+' : ''}${v} st` }
$('btn-go').onclick = async () => {
  const t = top()
  $('btn-go').disabled = true; $('progress-row').hidden = false; $('fill').style.width = '0%'
  try {
    const { id } = await api.convert(wavBlob(t.samples, t.sr), { voice: voice().name, mode: mode.value, steps: $('steps').value,
                                                                 pitch: $('pitch').value, name: takeName(), type: type.value, source: clipRef(t) })
    const clip = await api.waitForJob(id, (job) => {
      $('fill').style.width = `${job.progress * 100}%`
      $('progress-text').textContent = job.status !== 'running' ? '' : job.eta > 0 ? `${job.eta.toFixed(0)} s` : '…'
    })
    lib.warm[mode.value] = true
    api.library().then((l) => { lib.rates = l.rates }).catch(() => {})     // the server refits its estimate after every run
    await show({ label: clip.label, clip })
    toast(`Saved augmented ${clip.label} · ${type.value}`)
  } catch (e) { fail(e) }
  $('progress-row').hidden = true
  refresh()
}

// ---- render the chain offline into the next entry, and keep it
$('btn-render').onclick = async () => {
  const t = top()
  const entry = { samples: await renderChain(chain, t.samples, t.sr), sr: t.sr, label: `${t.label} · ${chainName(chain)}`, rendered: true }
  await show(entry)
  try {
    entry.clip = await api.saveAugmented(wavBlob(entry.samples, entry.sr), { name: entry.label, type: type.value, effects: chainName(chain), source: clipRef(t) })
    toast(`Saved augmented ${entry.clip.label} · ${type.value}`)
  } catch (e) { fail(e) }
  refresh()
}

// ---- undo and export
$('btn-undo').onclick = async () => { history.pop(); await load(top()) }
const deliver = (fmt, what) => {
  const t = top()
  if (!t?.clip) return
  download(api.exportUrl(t.clip, fmt), `${t.clip.label.replace(/\s+/g, '-')}.${fmt === 'opus' ? 'ogg' : fmt}`)
  toast(`Exported ${what}`)
}
$('btn-game').onclick = () => deliver('opus', 'for the game')
$('btn-share').onclick = () => deliver('mp3', 'for sharing')

loadLibrary().then(refresh).catch(fail)
renderChainCards()
icons()
