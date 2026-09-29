import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type FieldIssue } from '../api/client'
import {
  remotePreferences,
  type MatchItem,
  type MatchProfile,
  type RemotePreference,
} from '../api/schemas'
import { ChipListInput, ItemListInput } from '../components/MatchInputs'
import { ProfileTabs } from '../components/ProfileTabs'
import { ErrorMessage, Field, SuccessMessage } from '../components/ui'
import { describedBy, issueFor } from '../lib/forms'
import { remotePreferenceLabels } from '../lib/labels'
import { buttonClass, fieldsetClass, inputClass, legendClass } from '../lib/styles'

type ItemField = 'projects' | 'research' | 'activities' | 'experience'

/** Blank rows are dropped; blank descriptions mean "none". */
function cleanItems(items: MatchItem[]): MatchItem[] {
  return items
    .map((item) => ({
      name: item.name.trim(),
      description: item.description?.trim() || null,
    }))
    .filter((item) => item.name)
}

function toInput(form: MatchProfile): MatchProfile {
  return {
    ...form,
    projects: cleanItems(form.projects),
    research: cleanItems(form.research),
    activities: cleanItems(form.activities),
    experience: cleanItems(form.experience),
    availability_start: form.availability_start || null,
    availability_end: form.availability_end || null,
  }
}

function failureMessage(caught: unknown): string {
  // A proxy error or no answer at all: the backend may be waking up (ADR-009 §11).
  if (!(caught instanceof ApiError) || caught.status >= 500)
    return "The server didn't confirm the save (it may be waking up). Your changes are still here; try saving again."
  return caught.message
}

export function MatchProfilePage() {
  const [form, setForm] = useState<MatchProfile | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [issues, setIssues] = useState<FieldIssue[]>([])

  useEffect(() => {
    let active = true
    api
      .getMatchProfile()
      .then((profile) => active && setForm(profile))
      .catch(
        (caught: unknown) =>
          active &&
          setLoadError(
            caught instanceof Error
              ? caught.message
              : 'Could not load your Match Profile.',
          ),
      )
    return () => {
      active = false
    }
  }, [])

  if (loadError) return <ErrorMessage>{loadError}</ErrorMessage>
  if (!form)
    return (
      <div className="space-y-4">
        <ProfileTabs />
        <p role="status">Loading Match Profile…</p>
      </div>
    )
  const current = form
  const set = <K extends keyof MatchProfile>(name: K, value: MatchProfile[K]) => {
    setForm({ ...current, [name]: value })
    setMessage(null)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setMessage(null)
    setError(null)
    setIssues([])
    try {
      const saved = await api.saveMatchProfile(toInput(current))
      setForm(saved.match_profile)
      const rescored = saved.evaluated_opportunities
      setMessage(
        `Match Profile saved. ${rescored} opportunit${rescored === 1 ? 'y' : 'ies'} rescored` +
          (saved.unchanged_opportunities
            ? `, ${saved.unchanged_opportunities} unchanged.`
            : '.'),
      )
    } catch (caught) {
      setError(failureMessage(caught))
      if (caught instanceof ApiError) setIssues(caught.issues)
    } finally {
      setSaving(false)
    }
  }

  const chips = (
    name: 'skills' | 'courses' | 'interests' | 'preferred_locations',
    label: string,
    hint: string,
    max: number,
    maxLength = 100,
  ) => (
    <ChipListInput
      id={`match-${name}`}
      label={label}
      hint={hint}
      values={current[name]}
      max={max}
      maxLength={maxLength}
      error={issueFor(issues, name)}
      onChange={(values) => set(name, values)}
    />
  )

  const itemList = (name: ItemField, legend: string, noun: string, hint: string) => (
    <ItemListInput
      id={`match-${name}`}
      legend={legend}
      noun={noun}
      hint={hint}
      items={current[name]}
      max={25}
      error={issueFor(issues, name)}
      onChange={(items) => set(name, items)}
    />
  )

  const dateInput = (name: 'availability_start' | 'availability_end', label: string) => {
    const fieldError = issueFor(issues, name)
    return (
      <Field id={name} label={label} error={fieldError}>
        <input
          id={name}
          type="date"
          value={current[name] ?? ''}
          onChange={(event) => set(name, event.target.value || null)}
          {...describedBy(name, undefined, fieldError)}
          className={inputClass}
        />
      </Field>
    )
  }

  const formIssues = issues.filter((issue) => issue.field === null)
  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <ProfileTabs />
      <h1 className="text-2xl font-semibold">Match Profile</h1>
      <p className="text-slate-600">
        Used only to rank opportunities by fit. It never changes eligibility, and nothing
        is guessed: anything you leave empty counts as not measured. Saving rescores every
        opportunity once.
      </p>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Skills and coursework</legend>
        {chips(
          'skills',
          'Skills',
          'Languages, tools, and techniques, e.g. Python or C++. Press Enter to add.',
          50,
        )}
        {chips(
          'courses',
          'Courses',
          'Course titles, e.g. Data Science or AP Calculus BC.',
          50,
          150,
        )}
      </fieldset>

      {itemList(
        'projects',
        'Projects',
        'Project',
        'Describe what you built; shared keywords with a posting count toward fit.',
      )}
      {itemList('research', 'Research', 'Research item', 'Research you have done.')}
      {itemList(
        'activities',
        'Activities',
        'Activity',
        'Shown for your reference; activities do not affect fit in scoring v1.',
      )}
      {itemList(
        'experience',
        'Experience',
        'Experience item',
        'Shown for your reference; experience does not affect fit in scoring v1.',
      )}

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Interests and location</legend>
        {chips(
          'interests',
          'Interests',
          'Topics, e.g. machine learning or robotics.',
          30,
        )}
        {chips(
          'preferred_locations',
          'Preferred locations',
          'City or region as postings write it, e.g. San Jose, CA.',
          20,
        )}
        <Field
          id="remote_preference"
          label="Work mode preference"
          error={issueFor(issues, 'remote_preference')}
        >
          <select
            id="remote_preference"
            value={current.remote_preference ?? ''}
            onChange={(event) =>
              set(
                'remote_preference',
                (event.target.value || null) as RemotePreference | null,
              )
            }
            className={inputClass}
          >
            <option value="">Not set</option>
            {remotePreferences.map((p) => (
              <option key={p} value={p}>
                {remotePreferenceLabels[p]}
              </option>
            ))}
          </select>
        </Field>
      </fieldset>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Availability</legend>
        {dateInput('availability_start', 'Available from')}
        {dateInput('availability_end', 'Available until')}
      </fieldset>

      {formIssues.map((issue) => (
        <ErrorMessage key={issue.message}>{issue.message}</ErrorMessage>
      ))}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {saving && (
        <p role="status" className="text-slate-700">
          Saving and rescoring opportunities… This can take a few seconds.
        </p>
      )}
      {message && <SuccessMessage>{message}</SuccessMessage>}
      <button type="submit" disabled={saving} className={buttonClass}>
        {saving ? 'Saving…' : 'Save Match Profile'}
      </button>
    </form>
  )
}
