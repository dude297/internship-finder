import { useState, type FormEvent } from 'react'
import {
  applicationStatuses,
  eligibilityStatuses,
  remoteModes,
  type Source,
} from '../api/schemas'
import {
  applicationStatusLabels,
  eligibilityLabels,
  remoteModeLabels,
} from '../lib/labels'
import { inputClass, secondaryButtonClass } from '../lib/styles'

export type FilterName =
  | 'q'
  | 'availability'
  | 'source'
  | 'eligibility'
  | 'application_status'
  | 'remote_mode'
  | 'sort'

interface Props {
  values: Record<FilterName, string>
  sources: Source[]
  onChange: (name: FilterName, value: string) => void
}

function Select({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: [string, string][]
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={inputClass}
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </div>
  )
}

/** Server-side filters. The page keeps them in the URL, so they survive reloads and links. */
export function OpportunityFilters({ values, sources, onChange }: Props) {
  const [search, setSearch] = useState(values.q)

  function submit(event: FormEvent) {
    event.preventDefault()
    onChange('q', search.trim())
  }

  return (
    <div className="space-y-3 rounded border border-slate-200 p-3">
      <form role="search" onSubmit={submit} className="flex items-end gap-2">
        <div className="grow">
          <label htmlFor="filter-q" className="block text-sm font-medium">
            Search title or organization
          </label>
          <input
            id="filter-q"
            type="search"
            value={search}
            maxLength={200}
            onChange={(e) => setSearch(e.target.value)}
            className={inputClass}
          />
        </div>
        <button type="submit" className={secondaryButtonClass}>
          Search
        </button>
      </form>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Select
          id="filter-sort"
          label="Sort"
          value={values.sort}
          onChange={(v) => onChange('sort', v)}
          options={[
            ['recommended', 'Recommended'],
            ['newest', 'Newest'],
          ]}
        />
        <Select
          id="filter-availability"
          label="Show"
          value={values.availability}
          onChange={(v) => onChange('availability', v)}
          options={[
            ['open', 'Open and manual'],
            ['closed', 'Closed postings'],
            ['all', 'Everything'],
          ]}
        />
        <Select
          id="filter-source"
          label="Source"
          value={values.source}
          onChange={(v) => onChange('source', v)}
          options={[
            ['', 'All sources'],
            ['manual', 'Added by hand'],
            ...sources.map((s): [string, string] => [s.id, s.display_name]),
          ]}
        />
        <Select
          id="filter-eligibility"
          label="Eligibility"
          value={values.eligibility}
          onChange={(v) => onChange('eligibility', v)}
          options={[
            ['', 'Any'],
            ...eligibilityStatuses.map((s): [string, string] => [
              s,
              eligibilityLabels[s],
            ]),
            ['not_evaluated', 'Not evaluated'],
          ]}
        />
        <Select
          id="filter-application"
          label="Application"
          value={values.application_status}
          onChange={(v) => onChange('application_status', v)}
          options={[
            ['', 'Any'],
            ['tracked', 'Tracked'],
            ['untracked', 'Not tracked'],
            ...applicationStatuses.map((s): [string, string] => [
              s,
              applicationStatusLabels[s],
            ]),
          ]}
        />
        <Select
          id="filter-remote"
          label="Work mode"
          value={values.remote_mode}
          onChange={(v) => onChange('remote_mode', v)}
          options={[
            ['', 'Any'],
            ...remoteModes.map((m): [string, string] => [m, remoteModeLabels[m]]),
          ]}
        />
      </div>
    </div>
  )
}
