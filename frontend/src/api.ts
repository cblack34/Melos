// Pure request/response helpers for the Melos API (unit-tested in api.test.ts).

export interface GenerationFormValues {
  prompt: string
  tempo: string
  key: string
  timeSignature: string
  lyrics: string
  includeInstruments: string[]
  generationModel: string
  metaModel: string
}

export function buildGenerationRequest({
  prompt,
  tempo,
  key,
  timeSignature,
  lyrics,
  includeInstruments,
  generationModel,
  metaModel,
}: GenerationFormValues): Record<string, unknown> {
  const body: Record<string, unknown> = { prompt }
  if (tempo) body.tempo_bpm = Number(tempo)
  if (key) body.key = key
  if (timeSignature) {
    const [numerator, denominator] = timeSignature.split('/').map(Number)
    body.time_signature = { numerator, denominator }
  }
  if (lyrics.trim()) body.lyrics = lyrics
  if (includeInstruments.length) body.include_instruments = includeInstruments
  if (generationModel) body.generation_model = generationModel
  if (metaModel) body.meta_model = metaModel
  return body
}

export interface ModelOption {
  id: string
  label: string
}

export interface ModelOptions {
  generation: ModelOption[]
  meta: ModelOption[]
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

/** One SSE progress event from POST /api/generate/stream. */
export interface ProgressEvent {
  phase: string
  message?: string | null
  attempt?: number | null
  max_attempts?: number | null
  model_id?: string | null
  provider_response_id?: string | null
  reasons?: string[]
  filename?: string | null
  midi_base64?: string | null
}

/** Parse a single SSE frame block (between blank lines). Pure for unit tests. */
export function parseSseBlock(block: string): ProgressEvent | null {
  const trimmed = block.trim()
  if (!trimmed) return null
  const dataLines: string[] = []
  for (const line of trimmed.split('\n')) {
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }
  if (!dataLines.length) return null
  try {
    return JSON.parse(dataLines.join('\n')) as ProgressEvent
  } catch {
    return null
  }
}

/** Turn base64 MIDI from a completed event into a downloadable Blob. */
export function midiBlobFromBase64(b64: string): Blob {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new Blob([bytes], { type: 'audio/midi' })
}

/**
 * Consume POST /api/generate/stream. Calls onEvent for each progress event.
 * Resolves with the terminal completed event (includes MIDI). Rejects on
 * HTTP error, stream failure, or terminal phase=failed.
 */
export async function streamGenerate(
  body: Record<string, unknown>,
  onEvent: (event: ProgressEvent) => void,
  signal?: AbortSignal,
): Promise<ProgressEvent> {
  const response = await fetch('/api/generate/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    const responseBody = await response.json().catch(() => null)
    throw new Error(errorMessageFrom(response.status, responseBody))
  }
  if (!response.body) {
    throw new Error('Generate stream returned no body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed: ProgressEvent | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE frames are separated by a blank line.
    let splitAt = buffer.indexOf('\n\n')
    while (splitAt !== -1) {
      const frame = buffer.slice(0, splitAt)
      buffer = buffer.slice(splitAt + 2)
      const event = parseSseBlock(frame)
      if (event) {
        onEvent(event)
        if (event.phase === 'completed') completed = event
        if (event.phase === 'failed') {
          throw new Error(event.message || 'Generation failed')
        }
      }
      splitAt = buffer.indexOf('\n\n')
    }
  }

  // Flush a trailing frame without a final blank line.
  const tail = parseSseBlock(buffer)
  if (tail) {
    onEvent(tail)
    if (tail.phase === 'completed') completed = tail
    if (tail.phase === 'failed') {
      throw new Error(tail.message || 'Generation failed')
    }
  }

  if (!completed?.midi_base64) {
    throw new Error('Generate stream ended without a MIDI payload')
  }
  return completed
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
