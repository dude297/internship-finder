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
  work_authorized_us: '',
  needs_sponsorship_now: '',
  needs_sponsorship_future: '',
  us_citizen: '',
  us_permanent_resident: '',
  us_person_export_control: '',
  active_security_clearance: '',
  location: '',
}

// ADR-026: each answer is true / false / null (not provided) and is never derived from another.
const triStateFields: {
  name: keyof ProfileInput
  label: string
  hint: string
}[] = [
  {
    name: 'work_authorized_us',
    label: 'Currently authorized to work in the U.S.',
    hint: 'Legally allowed to work in the U.S. today, on any basis. Answering "Yes" here is separate from citizenship or residency.',
  },
  {
    name: 'needs_sponsorship_now',
    label: 'Need employer sponsorship now',
    hint: 'Would you need an employer to sponsor a work visa to start working?',
  },
  {
    name: 'needs_sponsorship_future',
    label: 'May need sponsorship in the future',
    hint: 'For example, a student whose work permission ends and who would need a visa later. Separate from the question above.',
  },
  {
    name: 'us_citizen',
    label: 'U.S. citizen',
    hint: 'Separate from the Citizenship(s) field above, which is used for citizenship-only requirements.',
  },
  {
    name: 'us_permanent_resident',
    label: 'U.S. permanent resident (green card holder)',
    hint: 'Answer independently of citizenship.',
  },
  {
    name: 'us_person_export_control',
    label: 'U.S. person for export control (ITAR/EAR)',
    hint: 'A legal term used by some employers: a U.S. citizen, a permanent resident, or a protected individual (such as a granted asylee or refugee). Answer it only if you know it applies; it is not worked out from your other answers.',
  },
  {
    name: 'active_security_clearance',
    label: 'Hold an active U.S. security clearance',
    hint: 'A clearance you hold today. Answer "No" only if you hold none.',
  },
]

const triValue = (value: boolean | null) => (value === null ? '' : value ? 'yes' : 'no')
const triInput = (value: string) =>
  value === 'yes' ? true : value === 'no' ? false : null

function toForm(profile: Profile | null): Form {
  const form = { ...emptyForm }
  if (!profile) return form
  for (const key of Object.keys(emptyForm) as (keyof Form)[]) {
    const value = profile[key]
    form[key] = Array.isArray(value)
      ? value.join(', ')
      : typeof value === 'boolean'
        ? triValue(value)
        : (value ?? '')
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
    work_authorized_us: triInput(form.work_authorized_us),
    needs_sponsorship_now: triInput(form.needs_sponsorship_now),
    needs_sponsorship_future: triInput(form.needs_sponsorship_future),
    us_citizen: triInput(form.us_citizen),
    us_permanent_resident: triInput(form.us_permanent_resident),
    us_person_export_control: triInput(form.us_person_export_control),
    active_security_clearance: triInput(form.active_security_clearance),
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

  const triSelect = ({ name, label, hint }: (typeof triStateFields)[number]) => {
    const fieldError = issueFor(issues, name)
    return (
      <Field key={name} id={name} label={label} hint={hint} error={fieldError}>
        <select
          id={name}
          value={current[name]}
          onChange={(event) => update(name, event.target.value)}
          {...describedBy(name, hint, fieldError)}
          className={inputClass}
        >
          <option value="">Prefer not to say / not provided</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
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

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Work authorization</legend>
        <p className="text-sm text-slate-600">
          Private, and used only to check postings whose requirements you have reviewed.
          Each question stands alone: nothing is worked out from your other answers (a
          citizen is not assumed to be "authorized", for example). Anything you leave as
          "Prefer not to say / not provided" shows "Needs verification" for the matching
          requirement, never a guess.
        </p>
        {triStateFields.map(triSelect)}
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
