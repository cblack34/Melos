import { describe, expect, it } from 'vitest'
import { buildGenerationRequest, filenameFrom } from './api'

describe('buildGenerationRequest', () => {
  it('sends only the prompt when no constraints are set', () => {
    expect(
      buildGenerationRequest({ prompt: 'a tune', tempo: '', key: '', timeSignature: '' }),
    ).toEqual({ prompt: 'a tune' })
  })

  it('includes only the constraints that are set', () => {
    expect(
      buildGenerationRequest({ prompt: 'a tune', tempo: '120', key: '', timeSignature: '' }),
    ).toEqual({ prompt: 'a tune', tempo_bpm: 120 })
    expect(
      buildGenerationRequest({ prompt: 'a tune', tempo: '', key: 'Am', timeSignature: '' }),
    ).toEqual({ prompt: 'a tune', key: 'Am' })
    expect(
      buildGenerationRequest({ prompt: 'a tune', tempo: '', key: '', timeSignature: '6/8' }),
    ).toEqual({ prompt: 'a tune', time_signature: { numerator: 6, denominator: 8 } })
  })

  it('maps every supplied constraint to the API shape', () => {
    expect(
      buildGenerationRequest({
        prompt: 'a waltz',
        tempo: '97.5',
        key: 'Dm',
        timeSignature: '3/4',
      }),
    ).toEqual({
      prompt: 'a waltz',
      tempo_bpm: 97.5,
      key: 'Dm',
      time_signature: { numerator: 3, denominator: 4 },
    })
  })
})

describe('filenameFrom', () => {
  it('extracts the server-provided filename', () => {
    const response = new Response(null, {
      headers: { 'content-disposition': 'attachment; filename="melos-sketch.mid"' },
    })
    expect(filenameFrom(response)).toBe('melos-sketch.mid')
  })

  it('falls back to song.mid without a disposition header', () => {
    expect(filenameFrom(new Response(null))).toBe('song.mid')
  })
})
