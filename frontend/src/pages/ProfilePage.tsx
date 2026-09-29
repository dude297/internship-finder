import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError, type FieldIssue } from '../api/client'
import {
  educationLevels,
  type EducationLevel,
  type Profile,
  type ProfileInput,
} from '../api/schemas'
import { ProfileTabs } from '../components/ProfileTabs'
import { ErrorMessage, Field, SuccessMessage } from '../components/ui'
import { describedBy, issueFor, orNull, parseCountries } from '../lib/forms'
import { educationLevelLabels } from '../lib/labels'
import { buttonClass, fieldsetClass, inputClass, legendClass } from '../lib/styles'

type Form = Record<keyof ProfileInput, string>

const emptyForm: Form = {
  current_education_level: '',
  current_grade: '',
  education_status_as_of: '',
  expected_graduation_date: '',
  expected_enrollment_date: '',
  expected_future_education_level: '',
  date_of_birth: '',
  citizenships: '',
  work_authorizations: '',
  location: '',
}

function toForm(profile: Profile | null): Form {
  const form = { ...emptyForm }
  if (!profile) return form
  for (const key of Object.keys(emptyForm) as (keyof Form)[]) {
    const value = profile[key]
    form[key] = Array.isArray(value) ? value.join(', ') : (value ?? '')
  }
  return form
}

function toInput(form: Form): ProfileInput {
  return {
    current_education_level: orNull(
      form.current_education_level,
    ) as EducationLevel | null,
    current_grade: orNull(form.current_grade),
    education_status_as_of: orNull(form.education_status_as_of),
    expected_graduation_date: orNull(form.expected_graduation_date),
    expected_enrollment_date: orNull(form.expected_enrollment_date),
    expected_future_education_level: orNull(
      form.expected_future_education_level,
    ) as EducationLevel | null,
    date_of_birth: orNull(form.date_of_birth),
    citizenships: parseCountries(form.citizenships),
    work_authorizations: parseCountries(form.work_authorizations),
    location: orNull(form.location),
  }
}

export function ProfilePage() {
  const [form, setForm] = useState<Form | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [issues, setIssues] = useState<FieldIssue[]>([])

  useEffect(() => {
    // Ignore responses that arrive after unmount or a re-run (e.g. StrictMode runs effects
    // twice), so a late response can't overwrite what the user already typed.
    let active = true
    api
      .getProfile()
      .then((profile) => active && setForm(toForm(profile)))
      .catch(
        (caught: unknown) =>
          active &&
          setLoadError(
            caught instanceof Error ? caught.message : 'Could not load your profile.',
          ),
      )
    return () => {
      active = false
    }
  }, [])

  if (loadError) return <ErrorMessage>{loadError}</ErrorMessage>
  if (!form) return <p role="status">Loading profile…</p>
  const current = form

  const update = (name: keyof Form, value: string) =>
    setForm({ ...current, [name]: value })

  const input = (name: keyof Form, label: string, type = 'text', hint?: string) => {
    const fieldError = issueFor(issues, name)
    return (
      <Field id={name} label={label} hint={hint} error={fieldError}>
        <input
          id={name}
          type={type}
          value={current[name]}
          onChange={(event) => update(name, event.target.value)}
          {...describedBy(name, hint, fieldError)}
          className={inputClass}
        />
      </Field>
    )
  }

  const levelSelect = (name: keyof Form, label: string) => {
    const fieldError = issueFor(issues, name)
    return (
      <Field id={name} label={label} error={fieldError}>
        <select
          id={name}
          value={current[name]}
          onChange={(event) => update(name, event.target.value)}
          {...describedBy(name, undefined, fieldError)}
          className={inputClass}
        >
          <option value="">Not set</option>
          {educationLevels.map((level) => (
            <option key={level} value={level}>
              {educationLevelLabels[level]}
            </option>
          ))}
        </select>
      </Field>
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setMessage(null)
    setError(null)
    setIssues([])
    try {
      const saved = await api.saveProfile(toInput(current))
      setForm(toForm(saved.profile))
      setMessage(
        saved.reevaluated_opportunities > 0
          ? 'Profile saved. Eligibility results updated.'
          : 'Profile saved.',
      )
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your profile.')
      if (caught instanceof ApiError) setIssues(caught.issues)
    } finally {
      setSaving(false)
    }
  }

  const formIssues = issues.filter((issue) => issue.field === null)
  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <ProfileTabs />
      <h1 className="text-2xl font-semibold">Your profile</h1>
      <p className="text-slate-600">
        Eligibility is checked against your expected status on each opportunity's dates,
        so record both where you are now and what comes next.
      </p>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Current education</legend>
        {levelSelect('current_education_level', 'Current level')}
        {input('current_grade', 'Current grade or year', 'text', 'For example: 12')}
        {input(
          'education_status_as_of',
          'Status as of',
          'date',
          'The date your current level was true. Required with a current level.',
        )}
      </fieldset>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Education transition</legend>
        {input('expected_graduation_date', 'Expected graduation', 'date')}
        {input('expected_enrollment_date', 'Expected college enrollment', 'date')}
        {levelSelect('expected_future_education_level', 'Expected future level')}
      </fieldset>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Eligibility information</legend>
        <p className="text-sm text-slate-600">
          These are optional. They're used only to check requirements such as a minimum
          age or citizenship. If you leave them blank, those checks show "Needs
          verification".
        </p>
        {input('date_of_birth', 'Date of birth (optional)', 'date')}
        {input(
          'citizenships',
          'Citizenship(s) (optional)',
          'text',
          'Two-letter country codes separated by commas, for example: US, CA',
        )}
        {input(
          'work_authorizations',
          'Work authorization(s) (optional)',
          'text',
          'Two-letter country codes separated by commas.',
        )}
        {input('location', 'Location (optional)')}
      </fieldset>

      {formIssues.map((issue) => (
        <ErrorMessage key={issue.message}>{issue.message}</ErrorMessage>
      ))}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {message && <SuccessMessage>{message}</SuccessMessage>}
      <button type="submit" disabled={saving} className={buttonClass}>
        {saving ? 'Saving…' : 'Save profile'}
      </button>
    </form>
  )
}
