// The effects: each builds the same Web Audio graph in the live context and in an offline render, so what you hear
// while it plays is what gets rendered. Pitch is playback rate (tape-style), not a node.

const impulse = (ctx, decay) => {
  const n = Math.ceil(ctx.sampleRate * decay), buf = ctx.createBuffer(1, n, ctx.sampleRate), d = buf.getChannelData(0)
  for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.exp(-6 * i / n)
  return buf
}
const wetDry = (ctx, make) => {
  const input = ctx.createGain(), output = ctx.createGain(), dry = ctx.createGain(), wet = ctx.createGain()
  input.connect(dry).connect(output)
  const set = make(input, wet)
  wet.connect(output)
  return { input, output, set: (p) => { dry.gain.value = 1 - p.mix; wet.gain.value = p.mix; set(p) } }
}
const filter = (type) => (ctx) => {
  const n = ctx.createBiquadFilter(); n.type = type
  return { input: n, output: n, set: (p) => { n.frequency.value = p.freq; n.Q.value = p.q } }
}
const hz = (v) => `${v} Hz`, two = (v) => v.toFixed(2), one = (v) => v.toFixed(1)
const cutoff = (min, max, value) => [{ key: 'freq', label: 'Cutoff', min, max, step: 10, value, fmt: hz },
                                     { key: 'q', label: 'Resonance', min: 0.1, max: 12, step: 0.1, value: 0.7, fmt: one }]
const mix = (value) => ({ key: 'mix', label: 'Mix', min: 0, max: 1, step: 0.01, value, fmt: two })

export const EFFECTS = {
  pitch: { label: 'Pitch', icon: 'arrow-up-down', category: 'Pitch', rate: true,
    params: [{ key: 'st', label: 'Semitones', min: -24, max: 12, step: 1, value: -12, fmt: (v) => `${v >= 0 ? '+' : ''}${v} st` }] },
  lowpass: { label: 'Low-pass', icon: 'waves', category: 'Tone', params: cutoff(100, 12000, 2400), build: filter('lowpass') },
  highpass: { label: 'High-pass', icon: 'waves', category: 'Tone', params: cutoff(20, 6000, 200), build: filter('highpass') },
  gain: { label: 'Gain', icon: 'volume-2', category: 'Drive',
    params: [{ key: 'db', label: 'Level', min: -30, max: 24, step: 0.5, value: 0, fmt: (v) => `${v} dB` }],
    build: (ctx) => { const n = ctx.createGain(); return { input: n, output: n, set: (p) => { n.gain.value = 10 ** (p.db / 20) } } } },
  distortion: { label: 'Distortion', icon: 'flame', category: 'Drive',
    params: [{ key: 'drive', label: 'Drive', min: 1, max: 60, step: 1, value: 12, fmt: String }],
    build: (ctx) => {
      const n = ctx.createWaveShaper(); n.oversample = '4x'
      return { input: n, output: n, set: (p) => {
        const k = p.drive / 4 + 0.1, c = new Float32Array(4096)
        for (let i = 0; i < 4096; i++) { const x = i / 2048 - 1; c[i] = Math.tanh(k * x) / Math.tanh(k) }
        n.curve = c
      } }
    } },
  delay: { label: 'Delay', icon: 'repeat', category: 'Space', tail: 2,
    params: [{ key: 'time', label: 'Time', min: 0.02, max: 1.5, step: 0.01, value: 0.3, fmt: (v) => `${two(v)} s` },
             { key: 'feedback', label: 'Feedback', min: 0, max: 0.9, step: 0.01, value: 0.35, fmt: two }, mix(0.3)],
    build: (ctx) => wetDry(ctx, (input, wet) => {
      const d = ctx.createDelay(2), fb = ctx.createGain()
      input.connect(d); d.connect(fb).connect(d); d.connect(wet)
      return (p) => { d.delayTime.value = p.time; fb.gain.value = p.feedback }
    }) },
  reverb: { label: 'Reverb', icon: 'cloud', category: 'Space', tail: 3,
    params: [{ key: 'decay', label: 'Decay', min: 0.2, max: 6, step: 0.1, value: 1.8, fmt: (v) => `${one(v)} s` }, mix(0.3)],
    build: (ctx) => wetDry(ctx, (input, wet) => {
      const c = ctx.createConvolver(); let decay = null
      input.connect(c).connect(wet)
      return (p) => { if (p.decay !== decay) { decay = p.decay; c.buffer = impulse(ctx, decay) } }
    }) },
  tremolo: { label: 'Tremolo', icon: 'activity', category: 'Motion',
    params: [{ key: 'rate', label: 'Rate', min: 0.5, max: 20, step: 0.1, value: 5, fmt: (v) => `${one(v)} Hz` },
             { key: 'depth', label: 'Depth', min: 0, max: 1, step: 0.01, value: 0.6, fmt: two }],
    build: (ctx) => {
      const g = ctx.createGain(), lfo = ctx.createOscillator(), depth = ctx.createGain()
      lfo.connect(depth).connect(g.gain); lfo.start()
      return { input: g, output: g, set: (p) => { lfo.frequency.value = p.rate; depth.gain.value = p.depth / 2; g.gain.value = 1 - p.depth / 2 } }
    } },
}

/** A fresh chain step with the effect's default parameters. */
export const newStep = (type, id) => ({ id, type, on: true, params: Object.fromEntries(EFFECTS[type].params.map((p) => [p.key, p.value])), node: null })
const on = (chain) => chain.filter((i) => i.on)
export const chainName = (chain) => on(chain).map((i) => i.type).join('-')
export const chainRate = (chain) => on(chain).filter((i) => EFFECTS[i.type].rate).reduce((r, i) => r * 2 ** (i.params.st / 12), 1)
const chainTail = (chain) => Math.max(0.05, ...on(chain).map((i) => EFFECTS[i.type].tail ?? 0))

/** Connect `from` through the chain's active node effects to `to`. Live playback reuses the nodes cached on each step. */
export function connectChain(ctx, chain, from, to, reuse) {
  let prev = from
  for (const i of on(chain)) {
    if (EFFECTS[i.type].rate) continue
    const node = reuse ? (i.node ??= EFFECTS[i.type].build(ctx)) : EFFECTS[i.type].build(ctx)
    node.set(i.params)
    prev.connect(node.input)
    prev = node.output
  }
  prev.connect(to)
}

/** Render mono samples through the chain offline; returns peak-normalised samples at the same rate. */
export async function renderChain(chain, samples, sr) {
  const r = chainRate(chain)
  const off = new OfflineAudioContext(1, Math.ceil(samples.length / r + chainTail(chain) * sr), sr)
  const buf = off.createBuffer(1, samples.length, sr)
  buf.copyToChannel(samples, 0)
  const src = off.createBufferSource(); src.buffer = buf; src.playbackRate.value = r
  connectChain(off, chain, src, off.destination, false)
  src.start()
  const out = (await off.startRendering()).getChannelData(0)
  let peak = 1e-6
  for (const s of out) peak = Math.max(peak, Math.abs(s))
  return Float32Array.from(out, (s) => s / peak * 0.95)
}

/** The card for one chain step; the page handles its events by delegation. */
export const cardHtml = (i, idx) => {
  const e = EFFECTS[i.type]
  return `<div class="rounded-xl border px-4 py-3 ${i.on ? '' : 'opacity-50'}" data-card="${i.id}">
    <div class="flex items-center gap-2">
      <i data-lucide="${e.icon}" class="h-4 w-4 text-sky-300"></i><span class="text-sm">${e.label}</span>
      <span class="ml-auto flex gap-1">
        <button class="btn-icon btn-sm" title="${i.on ? 'Bypass' : 'Enable'}" data-toggle><i data-lucide="${i.on ? 'power' : 'power-off'}"></i></button>
        <button class="btn-icon btn-sm" title="Move up" data-up ${idx === 0 ? 'disabled' : ''}><i data-lucide="chevron-up"></i></button>
        <button class="btn-icon btn-sm" title="Remove" data-remove><i data-lucide="x"></i></button>
      </span>
    </div>
    <div class="mt-2 grid gap-2">${e.params.map((p) => `
      <div class="flex items-center gap-3">
        <span class="label w-24">${p.label}</span>
        <input type="range" class="flex-1" min="${p.min}" max="${p.max}" step="${p.step}" value="${i.params[p.key]}" data-param="${p.key}">
        <span class="mono w-20 text-right text-xs text-slate-400" data-value="${p.key}">${p.fmt(i.params[p.key])}</span>
      </div>`).join('')}
    </div>
  </div>`
}
