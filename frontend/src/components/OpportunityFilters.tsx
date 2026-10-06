import { useState, type FormEvent } from 'react'
import {
  applicationStatuses,
  assessmentStatuses,
  eligibilityStatuses,
  remoteModes,
  opportunityTypes,
  type Source,
} from '../api/schemas'
import {
  applicationStatusLabels,
  assessmentLabels,
  eligibilityLabels,
  opportunityTypeLabels,
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
  | 'opportunity_type'
  | 'sort'
  | 'requirements_assessment_status'
  | 'requirement_review'
  | 'deadline_within'
  | 'needs_date_verification'
  | 'freshness'
  | 'discovered_within'
  | 'posted_within'
  | 'hidden'

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
            ['deadline', 'Deadline (soonest first)'],
            ['discovered', 'Recently discovered'],
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
        <Select
          id="filter-type"
          label="Type"
          value={values.opportunity_type}
          onChange={(v) => onChange('opportunity_type', v)}
          options={[
            ['', 'All types'],
            ...opportunityTypes.map((t): [string, string] => [
              t,
              opportunityTypeLabels[t],
            ]),
          ]}
        />
        <Select
          id="filter-requirements"
          label="Requirements"
          value={values.requirements_assessment_status}
          onChange={(v) => onChange('requirements_assessment_status', v)}
          options={[
            ['', 'Any'],
            ...assessmentStatuses.map((s): [string, string] => [s, assessmentLabels[s]]),
          ]}
        />
        <Select
          id="filter-requirement-review"
          label="Requirement suggestions"
          value={values.requirement_review}
          onChange={(v) => onChange('requirement_review', v)}
          options={[
            ['', 'Any'],
            ['pending', 'Has pending suggestions'],
            ['stale', 'Posting changed'],
            ['needs_review', 'Needs review'],
          ]}
        />
        <Select
          id="filter-deadline"
          label="Deadline"
          value={values.deadline_within}
          onChange={(v) => onChange('deadline_within', v)}
          options={[
            ['', 'Any'],
            ['7', 'Closing within 7 days'],
            ['14', 'Closing within 14 days'],
            ['30', 'Closing within 30 days'],
            ['has_deadline', 'Has a deadline'],
          ]}
        />
        <Select
          id="filter-date-verification"
          label="Date verification"
          value={values.needs_date_verification}
          onChange={(v) => onChange('needs_date_verification', v)}
          options={[
            ['', 'Any'],
            ['true', 'Needs date verification'],
          ]}
        />
        <Select
          id="filter-freshness"
          label="Freshness"
          value={values.freshness}
          onChange={(v) => onChange('freshness', v)}
          options={[
            ['', 'Any'],
            ['direct_verified', 'Direct ATS verified'],
            ['needs_review', 'Needs freshness review'],
          ]}
        />
        <Select
          id="filter-discovered"
          label="Discovered"
          value={values.discovered_within}
          onChange={(v) => onChange('discovered_within', v)}
          options={[
            ['', 'Any'],
            ['1', 'New today'],
            ['7', 'New this week'],
          ]}
        />
        <Select
          id="filter-posted"
          label="Posted"
          value={values.posted_within}
          onChange={(v) => onChange('posted_within', v)}
          options={[
            ['', 'Any'],
            ['7', 'Last 7 days'],
            ['30', 'Last 30 days'],
            ['90', 'Last 90 days'],
          ]}
        />
        <Select
          id="filter-hidden"
          label="Hidden"
          value={values.hidden}
          onChange={(v) => onChange('hidden', v)}
          options={[
            ['', 'Not hidden'],
            ['include', 'Include hidden'],
            ['only', 'Only hidden'],
          ]}
        />
      </div>
    </div>
  )
}
