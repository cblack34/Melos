// Pure request/response helpers for the Melos API (unit-tested in api.test.ts).

export interface GenerationFormValues {
  prompt: string
  tempo: string
  key: string
  timeSignature: string
  lyrics: string
}

export function buildGenerationRequest({
  prompt,
  tempo,
  key,
  timeSignature,
  lyrics,
}: GenerationFormValues): Record<string, unknown> {
  const body: Record<string, unknown> = { prompt }
  if (tempo) body.tempo_bpm = Number(tempo)
  if (key) body.key = key
  if (timeSignature) {
    const [numerator, denominator] = timeSignature.split('/').map(Number)
    body.time_signature = { numerator, denominator }
  }
  if (lyrics.trim()) body.lyrics = lyrics
  return body
}

export interface LyricRequestValues {
  prompt: string
  lyrics: string
  topic: string
}

export function buildLyricRequest({
  prompt,
  lyrics,
  topic,
}: LyricRequestValues): Record<string, unknown> {
  // The backend needs at least one signal and rejects blank strings, so send
  // only what the user actually filled in.
  const body: Record<string, unknown> = {}
  if (prompt.trim()) body.prompt = prompt
  if (lyrics.trim()) body.lyrics = lyrics
  if (topic.trim()) body.topic = topic
  return body
}

export function filenameFrom(response: Response): string {
  const disposition = response.headers.get('content-disposition')
  return disposition?.match(/filename="([^"]+)"/)?.[1] ?? 'song.mid'
}

/** The API's error `detail` is a string (our HTTPExceptions) or a list of
 * validation errors (FastAPI's 422 shape). Fall back to the status. */
export function errorMessageFrom(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => {
        const { msg, loc } = entry as { msg?: string; loc?: unknown[] }
        if (!msg) return undefined
        const field = Array.isArray(loc) ? loc[loc.length - 1] : undefined
        return typeof field === 'string' ? `${field}: ${msg}` : msg
      })
      .filter((msg): msg is string => Boolean(msg))
    if (messages.length) return messages.join('; ')
  }
  if (typeof detail === 'string' && detail) return detail
  return `Request failed (HTTP ${status})`
}
