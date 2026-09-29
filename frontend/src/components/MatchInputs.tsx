import { useState, type KeyboardEvent } from 'react'
import type { MatchItem } from '../api/schemas'
import {
  fieldsetClass,
  inputClass,
  legendClass,
  secondaryButtonClass,
} from '../lib/styles'

/** A list of short terms edited as removable chips. Adding never saves anything. */
export function ChipListInput({
  id,
  label,
  hint,
  values,
  max,
  maxLength,
  error,
  onChange,
}: {
  id: string
  label: string
  hint: string
  values: string[]
  max: number
  maxLength: number
  error?: string
  onChange: (values: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  const value = draft.trim()
  const duplicate = values.some((v) => v.toLowerCase() === value.toLowerCase())
  const canAdd = value !== '' && !duplicate && values.length < max

  function add() {
    if (!canAdd) return
    onChange([...values, value])
    setDraft('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault() // Enter adds a chip; it never submits the whole form
      add()
    }
  }

  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <div className="mt-1 flex gap-2">
        <input
          id={id}
          value={draft}
          maxLength={maxLength}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          aria-describedby={error ? `${id}-error` : `${id}-hint`}
          aria-invalid={error ? true : undefined}
          className={inputClass.replace('mt-1 ', '')}
        />
        <button
          type="button"
          onClick={add}
          disabled={!canAdd}
          className={secondaryButtonClass}
          aria-label={`Add to ${label}`}
        >
          Add
        </button>
      </div>
      <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
        {hint} ({values.length}/{max})
      </p>
      {error && (
        <p id={`${id}-error`} className="mt-1 text-sm text-red-700">
          {error}
        </p>
      )}
      {values.length > 0 && (
        <ul aria-label={`${label} added`} className="mt-2 flex flex-wrap gap-2">
          {values.map((v) => (
            <li
              key={v}
              className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-sm"
            >
              {v}
              <button
                type="button"
                onClick={() => onChange(values.filter((other) => other !== v))}
                aria-label={`Remove ${v}`}
                className="rounded-full px-1 text-slate-500 hover:bg-slate-200"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Named items with an optional description (projects, research, activities, experience). */
export function ItemListInput({
  id,
  legend,
  noun,
  hint,
  items,
  max,
  error,
  onChange,
}: {
  id: string
  legend: string
  noun: string
  hint: string
  items: MatchItem[]
  max: number
  error?: string
  onChange: (items: MatchItem[]) => void
}) {
  const update = (index: number, changes: Partial<MatchItem>) =>
    onChange(items.map((item, i) => (i === index ? { ...item, ...changes } : item)))

  return (
    <fieldset className={fieldsetClass}>
      <legend className={legendClass}>{legend}</legend>
      <p className="text-sm text-slate-600">{hint}</p>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {items.map((item, index) => (
        <div
          key={index}
          role="group"
          aria-label={`${noun} ${index + 1}`}
          className="space-y-2 rounded border border-slate-100 p-3"
        >
          <div>
            <label htmlFor={`${id}-${index}-name`} className="block text-sm font-medium">
              Name
            </label>
            <input
              id={`${id}-${index}-name`}
              value={item.name}
              maxLength={150}
              onChange={(event) => update(index, { name: event.target.value })}
              className={inputClass}
            />
          </div>
          <div>
            <label
              htmlFor={`${id}-${index}-description`}
              className="block text-sm font-medium"
            >
              Description (optional)
            </label>
            <textarea
              id={`${id}-${index}-description`}
              value={item.description ?? ''}
              maxLength={2000}
              rows={2}
              onChange={(event) => update(index, { description: event.target.value })}
              className={inputClass}
            />
          </div>
          <button
            type="button"
            onClick={() => onChange(items.filter((_, i) => i !== index))}
            className={secondaryButtonClass}
          >
            Remove {noun.toLowerCase()} {index + 1}
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...items, { name: '', description: null }])}
        disabled={items.length >= max}
        className={secondaryButtonClass}
      >
        Add {noun.toLowerCase()}
      </button>
    </fieldset>
  )
}
