import { useState, type FormEvent } from 'react'
import { buildLyricRequest, errorMessageFrom } from './api'

// Prefill the topic box. Not a fixed vocabulary — they are starting points the
// user edits, so a chip is just a shortcut for typing.
const TOPIC_CHIPS = [
  'Write a punk anthem',
  'Write an R&B ballad',
  'A late-night drive',
  'Leaving a small town',
  'Falling in love again',
]

interface Props {
  /** The song prompt, sent along so lyrics match the style being asked for. */
  prompt: string
  lyrics: string
  onChange: (lyrics: string) => void
}

export default function LyricsField({ prompt, lyrics, onChange }: Props) {
  const [composerOpen, setComposerOpen] = useState(false)
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function write(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const response = await fetch('/api/lyrics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildLyricRequest({ prompt, lyrics, topic })),
        signal: AbortSignal.timeout(300_000),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(errorMessageFrom(response.status, body))
      }
      const written = (await response.json()) as { lyrics: string }
      onChange(written.lyrics)
      setComposerOpen(false)
      setTopic('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="lyrics">
      <label htmlFor="lyrics">Lyrics</label>
      <textarea
        id="lyrics"
        value={lyrics}
        onChange={(e) => onChange(e.target.value)}
        placeholder={'Start writing lyrics…\n\n[verse 1]\n{soft brushed drums}'}
        rows={10}
      />
      <p className="hint">
        <code>[verse 1]</code> names a section, <code>{'{soft drums}'}</code> is a note
        to the arranger, everything else is sung.
      </p>

      {/* Click/focus, not hover: the composer has to be reachable by keyboard
          and on touch. */}
      <button
        type="button"
        className="ghost"
        aria-expanded={composerOpen}
        aria-controls="lyric-composer"
        onClick={() => setComposerOpen((open) => !open)}
      >
        ✦ Help me write lyrics
      </button>

      {composerOpen && (
        <div id="lyric-composer" className="composer">
          <div className="chips">
            {TOPIC_CHIPS.map((chip) => (
              <button
                type="button"
                key={chip}
                className="chip"
                onClick={() => setTopic(chip)}
              >
                {chip}
              </button>
            ))}
          </div>
          <div className="composer-input">
            <input
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="What should it be about?"
              aria-label="What the lyrics should be about"
              onKeyDown={(e) => {
                if (e.key === 'Enter') void write(e)
              }}
            />
            <button type="button" onClick={write} disabled={busy}>
              {busy ? 'Writing…' : 'Write'}
            </button>
          </div>
          {lyrics.trim() && (
            <p className="hint">Your existing lyrics are kept and built on.</p>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
