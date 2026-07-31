interface InstrumentOption {
  label: string
  value: string
}

// A compact cross-genre palette for modern rock, pop, country, worship, and
// blues. Values use the backend's canonical General MIDI names exactly;
// "drums" is its documented percussion pseudo-instrument.
const COMMON_INSTRUMENTS: InstrumentOption[] = [
  { label: 'Piano', value: 'Acoustic Grand Piano' },
  { label: 'Electric piano', value: 'Electric Piano 1' },
  { label: 'Acoustic guitar', value: 'Acoustic Guitar (steel)' },
  { label: 'Clean electric guitar', value: 'Electric Guitar (clean)' },
  { label: 'Overdriven guitar', value: 'Overdriven Guitar' },
  { label: 'Electric bass', value: 'Electric Bass (finger)' },
  { label: 'Synth bass', value: 'Synth Bass 1' },
  { label: 'Drums', value: 'drums' },
  { label: 'Drawbar organ', value: 'Drawbar Organ' },
  { label: 'Rock organ', value: 'Rock Organ' },
  { label: 'Fiddle', value: 'Fiddle' },
  { label: 'Banjo', value: 'Banjo' },
  { label: 'Harmonica', value: 'Harmonica' },
  { label: 'Tenor sax', value: 'Tenor Sax' },
  { label: 'Strings', value: 'String Ensemble 1' },
  { label: 'Trumpet', value: 'Trumpet' },
  { label: 'Warm synth pad', value: 'Pad 2 (warm)' },
  { label: 'Saw synth lead', value: 'Lead 2 (sawtooth)' },
]

const MAX_REQUIRED_INSTRUMENTS = 8

interface Props {
  selected: string[]
  onChange: (selected: string[]) => void
  disabled?: boolean
}

export default function InstrumentPicker({
  selected,
  onChange,
  disabled = false,
}: Props) {
  function setIncluded(instrument: string, isIncluded: boolean) {
    onChange(
      isIncluded
        ? [...selected, instrument]
        : selected.filter((value) => value !== instrument),
    )
  }

  const selectionSummary =
    selected.length === 0 ? 'Auto' : `${selected.length} required`

  return (
    <details className="instrument-picker">
      <summary>♫ Instruments · {selectionSummary}</summary>
      <fieldset disabled={disabled} aria-describedby="instrument-picker-help">
        <legend>Instruments to include</legend>
        <p id="instrument-picker-help" className="hint">
          Turn on up to {MAX_REQUIRED_INSTRUMENTS} instruments that must have
          their own tracks. Melos chooses the rest of the arrangement.
        </p>
        <div className="instrument-grid">
          {COMMON_INSTRUMENTS.map((instrument) => {
            const checked = selected.includes(instrument.value)
            const unavailable =
              disabled ||
              (!checked && selected.length >= MAX_REQUIRED_INSTRUMENTS)
            return (
              <label
                className={`instrument-switch${unavailable ? ' is-disabled' : ''}`}
                key={instrument.value}
              >
                <span>{instrument.label}</span>
                <input
                  className="switch-control"
                  type="checkbox"
                  role="switch"
                  checked={checked}
                  disabled={unavailable}
                  onChange={(event) =>
                    setIncluded(instrument.value, event.target.checked)
                  }
                />
              </label>
            )
          })}
        </div>
      </fieldset>
    </details>
  )
}
