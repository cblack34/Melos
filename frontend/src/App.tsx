import { useState, type FormEvent } from 'react'
import './App.css'

const KEYS = [
  'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'Cb',
  'Am', 'Em', 'Bm', 'F#m', 'C#m', 'G#m', 'D#m', 'A#m', 'Dm', 'Gm', 'Cm', 'Fm', 'Bbm',
  'Ebm', 'Abm',
]
const TIME_SIGNATURES = ['4/4', '3/4', '6/8', '2/4', '12/8']

function filenameFrom(response: Response): string {
  const disposition = response.headers.get('content-disposition')
  return disposition?.match(/filename="([^"]+)"/)?.[1] ?? 'song.mid'
}

interface GenerationFormValues {
  prompt: string
  tempo: string
  key: string
  timeSignature: string
}

function buildGenerationRequest({
  prompt,
  tempo,
  key,
  timeSignature,
}: GenerationFormValues): Record<string, unknown> {
  const body: Record<string, unknown> = { prompt }
  if (tempo) body.tempo_bpm = Number(tempo)
  if (key) body.key = key
  if (timeSignature) {
    const [numerator, denominator] = timeSignature.split('/').map(Number)
    body.time_signature = { numerator, denominator }
  }
  return body
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function App() {
  const [prompt, setPrompt] = useState('')
  const [tempo, setTempo] = useState('')
  const [songKey, setSongKey] = useState('')
  const [timeSignature, setTimeSignature] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function generate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const body = buildGenerationRequest({ prompt, tempo, key: songKey, timeSignature })
      const response = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        // Real AI generation on a local model can take minutes. The backend's
        // meta-resolution + generation calls run sequentially in one request
        // and can together approach ~25 min worst case (meta resolution falls
        // back to the openai SDK's 600s client default timeout since it sets
        // no explicit one, generation explicitly sets timeout=900 in
        // generation/llm.py), so give real margin over the server's own
        // timeouts rather than aborting a request the server would have
        // completed.
        signal: AbortSignal.timeout(1_800_000),
      })
      if (!response.ok) {
        const responseBody = await response.json().catch(() => null)
        const detail = Array.isArray(responseBody?.detail)
          ? responseBody.detail.map((d: { msg: string }) => d.msg).join('; ')
          : typeof responseBody?.detail === 'string'
            ? responseBody.detail
            : undefined
        throw new Error(detail ?? `Generation failed (HTTP ${response.status})`)
      }
      download(await response.blob(), filenameFrom(response))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="melos">
      <h1>Melos</h1>
      <p>Describe a song and download it as a multi-track MIDI file.</p>
      <form onSubmit={generate}>
        <label>
          Prompt
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="A dreamy lo-fi tune with a gentle melody…"
            rows={4}
            required
          />
        </label>
        <div className="constraints">
          <label>
            Tempo (BPM)
            <input
              type="number"
              min={20}
              max={400}
              step="any"
              value={tempo}
              onChange={(e) => setTempo(e.target.value)}
              placeholder="auto"
            />
          </label>
          <label>
            Key
            <select value={songKey} onChange={(e) => setSongKey(e.target.value)}>
              <option value="">auto</option>
              {KEYS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label>
            Time signature
            <select
              value={timeSignature}
              onChange={(e) => setTimeSignature(e.target.value)}
            >
              <option value="">auto</option>
              {TIME_SIGNATURES.map((ts) => (
                <option key={ts} value={ts}>
                  {ts}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button type="submit" disabled={busy || !prompt.trim()}>
          {busy ? 'Generating…' : 'Generate MIDI'}
        </button>
        {error && <p role="alert" className="error">{error}</p>}
      </form>
    </main>
  )
}
