import { describe, expect, it } from 'vitest'
import {
  buildGenerationRequest,
  buildLyricRequest,
  errorMessageFrom,
  filenameFrom,
} from './api'

const EMPTY = {
  prompt: 'a tune',
  tempo: '',
  key: '',
  timeSignature: '',
  lyrics: '',
  generationModel: '',
  metaModel: '',
}

describe('buildGenerationRequest', () => {
  it('sends only the prompt when no constraints are set', () => {
    expect(buildGenerationRequest(EMPTY)).toEqual({ prompt: 'a tune' })
  })

  it('includes only the constraints that are set', () => {
    expect(buildGenerationRequest({ ...EMPTY, tempo: '120' })).toEqual({
      prompt: 'a tune',
      tempo_bpm: 120,
    })
    expect(buildGenerationRequest({ ...EMPTY, key: 'Am' })).toEqual({
      prompt: 'a tune',
      key: 'Am',
    })
    expect(buildGenerationRequest({ ...EMPTY, timeSignature: '6/8' })).toEqual({
      prompt: 'a tune',
      time_signature: { numerator: 6, denominator: 8 },
    })
  })

  it('maps every supplied constraint to the API shape', () => {
    expect(
      buildGenerationRequest({
        prompt: 'a waltz',
        tempo: '97.5',
        key: 'Dm',
        timeSignature: '3/4',
        lyrics: '[verse 1]\nCarry me home',
        generationModel: 'anthropic/claude-sonnet-5',
        metaModel: 'openai/gpt-5-nano',
      }),
    ).toEqual({
      prompt: 'a waltz',
      tempo_bpm: 97.5,
      key: 'Dm',
      time_signature: { numerator: 3, denominator: 4 },
      lyrics: '[verse 1]\nCarry me home',
      generation_model: 'anthropic/claude-sonnet-5',
      meta_model: 'openai/gpt-5-nano',
    })
  })

  it('omits model overrides when left at the server default', () => {
    expect(buildGenerationRequest(EMPTY)).toEqual({ prompt: 'a tune' })
  })

  it('omits whitespace-only lyrics so the song stays an instrumental', () => {
    expect(buildGenerationRequest({ ...EMPTY, lyrics: '  \n\t ' })).toEqual({
      prompt: 'a tune',
    })
  })
})

describe('buildLyricRequest', () => {
  it('sends only the fields the user filled in', () => {
    // The backend requires at least one signal and rejects blank strings.
    expect(buildLyricRequest({ prompt: '', lyrics: '', topic: 'a road trip' })).toEqual({
      topic: 'a road trip',
    })
  })

  it('passes style and existing lyrics through for revision', () => {
    expect(
      buildLyricRequest({
        prompt: 'dreamy lo-fi',
        lyrics: '[verse 1]\nhalf a line',
        topic: 'rain',
      }),
    ).toEqual({
      prompt: 'dreamy lo-fi',
      lyrics: '[verse 1]\nhalf a line',
      topic: 'rain',
    })
  })

  it('drops whitespace-only values', () => {
    expect(buildLyricRequest({ prompt: '  ', lyrics: '\n', topic: 'x' })).toEqual({
      topic: 'x',
    })
  })

  it('returns an empty body when everything is blank', () => {
    expect(buildLyricRequest({ prompt: '  ', lyrics: '\n', topic: '' })).toEqual({})
  })
})

describe('errorMessageFrom', () => {
  it('joins FastAPI validation errors', () => {
    const body = { detail: [{ msg: 'too short' }, { msg: 'not a key' }] }
    expect(errorMessageFrom(422, body)).toBe('too short; not a key')
  })

  it('uses a plain string detail', () => {
    expect(errorMessageFrom(502, { detail: 'generation failed: nope' })).toBe(
      'generation failed: nope',
    )
  })

  it('falls back to the status when there is no usable detail', () => {
    expect(errorMessageFrom(500, null)).toBe('Request failed (HTTP 500)')
    expect(errorMessageFrom(500, { detail: [] })).toBe('Request failed (HTTP 500)')
    expect(errorMessageFrom(500, { detail: '' })).toBe('Request failed (HTTP 500)')
    expect(errorMessageFrom(500, { detail: [{ loc: ['body', 'topic'] }] })).toBe(
      'Request failed (HTTP 500)',
    )
  })

  it('prefixes the field name when validation errors include a loc', () => {
    const body = { detail: [{ msg: 'String should have at most 1000 characters', loc: ['body', 'topic'] }] }
    expect(errorMessageFrom(422, body)).toBe(
      'topic: String should have at most 1000 characters',
    )
  })

  it('drops entries without a usable message but keeps the rest', () => {
    expect(
      errorMessageFrom(422, { detail: [{ msg: 'too short' }, { loc: ['body'] }] }),
    ).toBe('too short')
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
