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
const lfoRate = (value) => ({ key: 'rate', label: 'Rate', min: 0.05, max: 10, step: 0.05, value, fmt: (v) => `${two(v)} Hz` })
/** A WaveShaper with a curve computed from the parameters. */
const shaper = (curve) => (ctx) => {
  const n = ctx.createWaveShaper(); n.oversample = '4x'
  return { input: n, output: n, set: (p) => { const c = new Float32Array(8192); for (let i = 0; i < c.length; i++) c[i] = curve(i / 4096 - 1, p); n.curve = c } }
}
/** An oscillator driving an AudioParam through a gain, for chorus, phaser and tremolo style modulation. */
const lfo = (ctx, param) => { const osc = ctx.createOscillator(), depth = ctx.createGain(); osc.connect(depth).connect(param); osc.start(); return { osc, depth } }

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
    build: shaper((x, p) => { const k = p.drive / 4 + 0.1; return Math.tanh(k * x) / Math.tanh(k) }) },
  clip: { label: 'Hard clip', icon: 'square', category: 'Drive',
    params: [{ key: 'db', label: 'Threshold', min: -40, max: 0, step: 0.5, value: -6, fmt: (v) => `${v} dB` }],
    build: shaper((x, p) => { const t = 10 ** (p.db / 20); return Math.max(-t, Math.min(t, x)) / t }) },
  wavefold: { label: 'Wavefolder', icon: 'triangle', category: 'Drive',
    params: [{ key: 'drive', label: 'Drive', min: 1, max: 12, step: 0.1, value: 3, fmt: one }],
    build: shaper((x, p) => { const y = ((x * p.drive + 1) % 4 + 4) % 4; return Math.abs(y - 2) - 1 }) },
  crush: { label: 'Bitcrush', icon: 'grid-2x2', category: 'Drive',
    params: [{ key: 'bits', label: 'Bits', min: 2, max: 16, step: 0.5, value: 8, fmt: one }],
    build: shaper((x, p) => { const levels = 2 ** p.bits / 2; return Math.round(x * levels) / levels }) },
  ringmod: { label: 'Ring mod', icon: 'circle-dot', category: 'Drive',
    params: [{ key: 'hz', label: 'Carrier', min: 1, max: 2000, step: 1, value: 60, fmt: hz }, mix(1)],
    build: (ctx) => wetDry(ctx, (input, wet) => {
      const g = ctx.createGain(); g.gain.value = 0                       // the carrier multiplies the signal through the gain
      const { osc } = lfo(ctx, g.gain)
      input.connect(g).connect(wet)
      return (p) => { osc.frequency.value = p.hz }
    }) },
  compressor: { label: 'Compressor', icon: 'shrink', category: 'Drive',
    params: [{ key: 'threshold', label: 'Threshold', min: -60, max: 0, step: 1, value: -18, fmt: (v) => `${v} dB` },
             { key: 'ratio', label: 'Ratio', min: 1, max: 20, step: 0.5, value: 4, fmt: one },
             { key: 'attack', label: 'Attack', min: 1, max: 200, step: 1, value: 5, fmt: (v) => `${v} ms` },
             { key: 'release', label: 'Release', min: 10, max: 1000, step: 10, value: 120, fmt: (v) => `${v} ms` }],
    build: (ctx) => {
      const n = ctx.createDynamicsCompressor()
      return { input: n, output: n, set: (p) => { n.threshold.value = p.threshold; n.ratio.value = p.ratio; n.attack.value = p.attack / 1000; n.release.value = p.release / 1000 } }
    } },
  phone: { label: 'Telephone', icon: 'phone', category: 'Tone',
    params: [mix(1)],
    build: (ctx) => wetDry(ctx, (input, wet) => {
      const hp = ctx.createBiquadFilter(), lp = ctx.createBiquadFilter(), grit = ctx.createWaveShaper()
      hp.type = 'highpass'; hp.frequency.value = 300; lp.type = 'lowpass'; lp.frequency.value = 3400
      grit.curve = Float32Array.from({ length: 4096 }, (_, i) => Math.tanh(3 * (i / 2048 - 1)) / Math.tanh(3))
      input.connect(hp).connect(lp).connect(grit).connect(wet)
      return () => {}
    }) },
  chorus: { label: 'Chorus', icon: 'waves', category: 'Motion',
    params: [lfoRate(1), { key: 'depth', label: 'Depth', min: 0, max: 10, step: 0.1, value: 2.5, fmt: (v) => `${one(v)} ms` }, mix(0.5)],
    build: (ctx) => wetDry(ctx, (input, wet) => {
      const d = ctx.createDelay(0.1); d.delayTime.value = 0.02
      const { osc, depth } = lfo(ctx, d.delayTime)
      input.connect(d).connect(wet)
      return (p) => { osc.frequency.value = p.rate; depth.gain.value = p.depth / 1000 }
    }) },
  phaser: { label: 'Phaser', icon: 'orbit', category: 'Motion',
    params: [lfoRate(0.5), { key: 'depth', label: 'Depth', min: 0, max: 1, step: 0.01, value: 0.7, fmt: two }, mix(0.5)],
    build: (ctx) => wetDry(ctx, (input, wet) => {
      const stages = [0, 1, 2, 3].map(() => { const f = ctx.createBiquadFilter(); f.type = 'allpass'; f.frequency.value = 800; f.Q.value = 0.7; return f })
      const { osc, depth } = lfo(ctx, stages[0].frequency)
      stages.slice(1).forEach((f) => depth.connect(f.frequency))
      stages.reduce((prev, f) => prev.connect(f), input).connect(wet)
      return (p) => { osc.frequency.value = p.rate; depth.gain.value = 600 * p.depth }
    }) },
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
    params: [lfoRate(5), { key: 'depth', label: 'Depth', min: 0, max: 1, step: 0.01, value: 0.6, fmt: two }],
    build: (ctx) => {
      const g = ctx.createGain()
      const { osc, depth } = lfo(ctx, g.gain)
      return { input: g, output: g, set: (p) => { osc.frequency.value = p.rate; depth.gain.value = p.depth / 2; g.gain.value = 1 - p.depth / 2 } }
    } },
}

/** A fresh chain step with the effect's default parameters. */
export const newStep = (type, id) => ({ id, type, on: true, params: Object.fromEntries(EFFECTS[type].params.map((p) => [p.key, p.value])), node: null })
const on = (chain) => chain.filter((i) => i.on)
export const chainName = (chain) => on(chain).map((i) => i.type).join('-')
export const chainKey = (chain) => JSON.stringify(on(chain).map((i) => [i.type, i.params]))   // the chain with its settings, to tell renders apart
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
