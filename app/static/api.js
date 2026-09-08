// The page's only contact with the server.
const json = async (r) => { if (!r.ok) throw new Error((await r.text()) || r.statusText); return r.json() }
const form = (fields, blob) => {
  const f = new FormData()
  if (blob) f.append('file', blob, 'audio.wav')
  for (const [k, v] of Object.entries(fields)) if (v !== undefined && v !== null) f.append(k, v)
  return f
}

export const api = {
  library: () => fetch('/api/library').then(json),
  saveOriginal: (blob, name, type, mic) => fetch('/api/originals', { method: 'POST', body: form({ name, type, mic: mic && JSON.stringify(mic) }, blob) }).then(json),
  updateOriginal: (clipName, blob) => fetch(`/api/originals/${clipName}`, { method: 'PUT', body: form({}, blob) }).then(json),
  convert: (blob, fields) => fetch('/api/convert', { method: 'POST', body: form(fields, blob) }).then(json),
  job: (id) => fetch(`/api/jobs/${id}`).then(json),
  /** Resolve with the finished job's clip, calling onProgress(job) as it runs; a busy server is ridden out, not given up on. */
  waitForJob: (id, onProgress) => new Promise((resolve, reject) => {
    let misses = 0
    const poll = async () => {
      let job
      try { job = await api.job(id); misses = 0 } catch (e) { if (++misses > 60) return reject(e); return setTimeout(poll, 1000) }
      onProgress(job)
      if (job.status === 'done') resolve(job.clip)
      else if (job.status === 'failed') reject(new Error(job.error))
      else setTimeout(poll, 500)
    }
    poll()
  }),
  saveAugmented: (blob, fields) => fetch('/api/augmented', { method: 'POST', body: form(fields, blob) }).then(json),
  createVoice: (fields) => fetch('/api/voices', { method: 'POST', body: form(fields) }).then(json),
  updateClip: (clip, fields) => fetch(`/api/clips/${clip.kind}/${clip.name}`, { method: 'PATCH', body: form(fields) }).then(json),
  deleteClip: (clip) => fetch(`/api/clips/${clip.kind}/${clip.name}`, { method: 'DELETE' }).then(json),
  exportUrl: (clip, fmt) => `/api/export/${clip.kind}/${clip.name}.${fmt}`,
}
