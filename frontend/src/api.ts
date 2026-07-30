// Pure request/response helpers for /api/generate (unit-tested in api.test.ts).

export interface GenerationFormValues {
  prompt: string
  tempo: string
  key: string
  timeSignature: string
}

export function buildGenerationRequest({
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

export function filenameFrom(response: Response): string {
  const disposition = response.headers.get('content-disposition')
  return disposition?.match(/filename="([^"]+)"/)?.[1] ?? 'song.mid'
}
