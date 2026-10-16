import { useEffect, useRef, useState } from 'react'
import { searchPlaces } from '../api'

// Text box with suggestions. `value` is either a string (still typing) or
// a picked place {label, lon, lat}.
export default function PlaceInput({ label, value, onChange, placeholder }) {
  const text = typeof value === 'string' ? value : value?.label || ''
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const boxRef = useRef(null)

  useEffect(() => {
    if (typeof value !== 'string' || value.trim().length < 3) {
      setResults([])
      return
    }
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(value, ctrl.signal)
        .then((r) => {
          setResults(r)
          setActive(-1)
        })
        .catch(() => {})
    }, 250)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [value])

  useEffect(() => {
    const close = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const pick = (place) => {
    onChange(place)
    setOpen(false)
  }

  const onKeyDown = (e) => {
    if (!open || !results.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      pick(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="field place" ref={boxRef}>
      <label>{label}</label>
      <input
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        autoComplete="off"
        required
      />
      {open && results.length > 0 && (
        <ul className="suggestions">
          {results.map((r, i) => (
            <li
              key={`${r.lon},${r.lat},${i}`}
              className={i === active ? 'active' : ''}
              onMouseDown={() => pick(r)}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
