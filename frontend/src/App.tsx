import { useEffect, useRef, useState, type FormEvent } from 'react'
import ActivityLog, { type LogEntry } from './ActivityLog'
import {
  buildGenerationRequest,
  midiBlobFromBase64,
  streamGenerate,
} from './api'
import LyricsField from './LyricsField'
import ModelPicker from './ModelPicker'
import './App.css'

const KEYS = [
  'C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'Cb',
  'Am', 'Em', 'Bm', 'F#m', 'C#m', 'G#m', 'D#m', 'A#m', 'Dm', 'Gm', 'Cm', 'Fm', 'Bbm',
  'Ebm', 'Abm',
]
const TIME_SIGNATURES = ['4/4', '3/4', '6/8', '2/4', '12/8']

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
  const [lyrics, setLyrics] = useState('')
  const [generationModel, setGenerationModel] = useState('')
  const [metaModel, setMetaModel] = useState('')
  const [busy, setBusy] = useState(false)
  const [lyricsBusy, setLyricsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [logEntries, setLogEntries] = useState<LogEntry[]>([])
  const [elapsedMs, setElapsedMs] = useState<number | null>(null)
  const nextId = useRef(0)
  const runStarted = useRef<number | null>(null)

  useEffect(() => {
    if (!busy) return
    const tick = window.setInterval(() => {
      if (runStarted.current != null) {
        setElapsedMs(Date.now() - runStarted.current)
      }
    }, 250)
    return () => window.clearInterval(tick)
  }, [busy])

  async function generate(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setLogEntries([])
    nextId.current = 0
    runStarted.current = Date.now()
    setElapsedMs(0)
    try {
      const body = buildGenerationRequest({
        prompt,
        tempo,
        key: songKey,
        timeSignature,
        lyrics,
        generationModel,
        metaModel,
      })
      // Real AI generation on a local model can take minutes. The backend's
      // meta-resolution + generation calls run sequentially and can together
      // approach ~25 min worst case, so give real margin over the server's
      // own timeouts rather than aborting a request the server would have
      // completed.
      const completed = await streamGenerate(
        body,
        (progress) => {
          const at = runStarted.current != null ? Date.now() - runStarted.current : 0
          const id = nextId.current++
          setLogEntries((prev) => [...prev, { id, event: progress, at }])
        },
        AbortSignal.timeout(1_800_000),
      )
      const filename = completed.filename || 'song.mid'
      download(midiBlobFromBase64(completed.midi_base64!), filename)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
      if (runStarted.current != null) {
        setElapsedMs(Date.now() - runStarted.current)
      }
    }
  }

  return (
    <div className="melos-layout">
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
          <LyricsField
            prompt={prompt}
            lyrics={lyrics}
            onChange={setLyrics}
            onBusyChange={setLyricsBusy}
          />
          <ModelPicker
            generationModel={generationModel}
            metaModel={metaModel}
            onGenerationModelChange={setGenerationModel}
            onMetaModelChange={setMetaModel}
          />
          <button type="submit" disabled={busy || lyricsBusy || !prompt.trim()}>
            {busy ? 'Generating…' : 'Generate MIDI'}
          </button>
          {error && <p role="alert" className="error">{error}</p>}
        </form>
      </main>
      <ActivityLog entries={logEntries} elapsedMs={elapsedMs} running={busy} />
    </div>
  )
}
