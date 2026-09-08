// The page. One waveform holds a history of take, conversion and render; everything else reads or feeds it.
import { $, icons, setButton, toast, shell, segment, decodeFile, wavBlob, download } from './lab.js'
import { modal, dialog } from './modal.js'
import { createEditor } from './editor.js'
import { EFFECTS, newStep, chainName, chainRate, connectChain, renderChain, cardHtml } from './effects.js'
import { api } from './api.js'

shell(`<div id="type" class="seg">
         <button data-value="Voice" class="active" title="A voice line"><i data-lucide="mic-vocal"></i>Voice</button>
         <button data-value="SFX" title="A sound effect"><i data-lucide="drum"></i>SFX</button>
       </div>`)

// ---- state
let lib = { voices: [], clips: [], rates: {}, warm: {}, kokoro: {} }
const history = []                                    // { samples, sr, label, clip?, rendered? }
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
const estimateSeconds = () => {                        // the same fit as the server's, from the rates it serves
  const r = lib.rates[mode.value], t = top(), steps = +$('steps').value
  return r && t ? r.fixed + r.per_step * steps + r.per_step_second * (t.samples.length / t.sr) * steps + (lib.warm[mode.value] ? 0 : r.cold) : 0
}
const refresh = () => {
  const t = top()
  $('btn-go').disabled = !t || t.rendered || !lib.voices.length
  $('btn-render').disabled = !t || !chain.some((i) => i.on)
  $('btn-undo').disabled = history.length < 2
  $('btn-game').disabled = $('btn-share').disabled = !t?.clip || history.length < 2
  $('est').textContent = t && !t.rendered && type.value === 'Voice' ? `~${(estimateSeconds() / 60).toFixed(1)} min` : ''
  wire()
}
let expecting = null                                  // what the next 'ready' means: a fresh take, or an entry already pushed
editor.onReady(async () => {
  const what = expecting
  expecting = 'crop'                                  // decided before any await, so a second 'ready' cannot save the take twice
  if (what === 'take') {
    history.length = 0
    const entry = { ...editor.samples(0, undefined), label: takeName() || 'take' }
    history.push(entry)
    try {
      entry.clip = await api.saveOriginal(wavBlob(entry.samples, entry.sr), takeName(), type.value)
      entry.label = entry.clip.label
      toast(`Saved original ${entry.clip.label} · ${type.value}`)
    } catch (e) { fail(e) }
  } else if (what === 'crop' && top()) {             // a crop inside the editor reloads it: keep the entry, update its audio
    const t = top()
    Object.assign(t, editor.samples(0, undefined))
    if (t.clip?.kind === 'original') api.updateOriginal(t.clip.name, wavBlob(t.samples, t.sr)).catch(fail)
  }
  refresh()
})
const fresh = () => { expecting = 'take' }
const show = async (entry) => { history.push(entry); expecting = 'crop'; await editor.load(entry.clip?.url ?? wavBlob(entry.samples, entry.sr)) }
$('editor').addEventListener('recording', (e) => { if (e.detail) { fresh(); history.length = 0; refresh() } })
$('btn-import').onclick = () => $('file').click()
$('file').onchange = async (e) => {
  const file = e.target.files[0]
  if (!file) return
  if (!takeName()) $('name').value = file.name.replace(/\.[^.]+$/, '')
  fresh()
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
    if (o) history.push({ ...(await decodeFile(o.url)), label: o.label, clip: o })
  }
  history.push({ ...(await decodeFile(c.url)), label: c.label, clip: c, rendered: !!c.effects })
  expecting = 'crop'
  await editor.load(c.url)
}
const remove = async (c) => {
  await api.deleteClip(c)
  history.forEach((t) => { if (t.clip?.kind === c.kind && t.clip?.name === c.name) delete t.clip })
  refresh()
}
$('btn-library').onclick = async () => modal('Library', (await loadLibrary()).clips.map((c) => ({
  label: c.label, meta: `${c.when} · ${c.seconds.toFixed(1)} s`, when: c.when, seconds: c.seconds,
  facets: { Type: c.type, Stage: c.kind === 'original' ? 'Original' : 'Augmented', ...(c.voice ? { Voice: c.voice, Mode: c.mode } : {}),
            ...(c.effects ? { Effects: c.effects } : {}) },
  pick: () => pick(c), remove: () => remove(c),
})), { sorts: [
  { label: 'Newest', by: (a, b) => b.when.localeCompare(a.when) },
  { label: 'Oldest', by: (a, b) => a.when.localeCompare(b.when) },
  { label: 'Name', by: (a, b) => a.label.localeCompare(b.label) },
  { label: 'Longest', by: (a, b) => b.seconds - a.seconds },
] })

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
  label: e.label, facets: { Category: e.category },
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
      $('progress-text').textContent = job.status === 'running' ? `${job.eta.toFixed(0)} s` : ''
    })
    lib.warm[mode.value] = true
    await show({ ...(await decodeFile(clip.url)), label: clip.label, clip })
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
$('btn-undo').onclick = async () => { history.pop(); expecting = 'crop'; await editor.load(wavBlob(top().samples, top().sr)) }
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
