import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api, ApiError, type FieldIssue } from '../api/client'
import {
  assessmentStatuses,
  opportunityTypes,
  remoteModes,
  type AssessmentStatus,
  type OpportunityDetail,
  type OpportunityInput,
  type OpportunityType,
  type RemoteMode,
} from '../api/schemas'
import { RequirementsEditor } from '../components/RequirementsEditor'
import { ErrorMessage, Field } from '../components/ui'
import { describedBy, issueFor, orNull } from '../lib/forms'
import {
  assessmentDescriptions,
  assessmentLabels,
  opportunityTypeLabels,
  remoteModeLabels,
} from '../lib/labels'
import { toRequirementInput, toRow, type RequirementRow } from '../lib/requirements'
import { buttonClass, fieldsetClass, inputClass, legendClass } from '../lib/styles'

interface Form {
  title: string
  organization: string
  opportunity_type: OpportunityType
  description: string
  application_url: string
  location: string
  remote_mode: RemoteMode | ''
  application_deadline: string
  start_date: string
  end_date: string
  requirements_assessment_status: AssessmentStatus
  requirements: RequirementRow[]
}

type TextField = Exclude<
  keyof Form,
  'requirements' | 'requirements_assessment_status' | 'opportunity_type' | 'remote_mode'
>

const emptyForm: Form = {
  title: '',
  organization: '',
  opportunity_type: 'internship',
  description: '',
  application_url: '',
  location: '',
  remote_mode: '',
  application_deadline: '',
  start_date: '',
  end_date: '',
  // A new opportunity stays unassessed unless the owner says otherwise.
  requirements_assessment_status: 'unassessed',
  requirements: [],
}

function toForm(o: OpportunityDetail): Form {
  return {
    title: o.title,
    organization: o.organization,
    opportunity_type: o.opportunity_type,
    description: o.description ?? '',
    application_url: o.application_url ?? '',
    location: o.location ?? '',
    remote_mode: o.remote_mode ?? '',
    application_deadline: o.application_deadline ?? '',
    start_date: o.start_date ?? '',
    end_date: o.end_date ?? '',
    requirements_assessment_status: o.requirements_assessment_status,
    requirements: o.requirements.map(toRow),
  }
}

function toInput(form: Form): OpportunityInput {
  return {
    title: form.title.trim(),
    organization: form.organization.trim(),
    opportunity_type: form.opportunity_type,
    description: orNull(form.description),
    application_url: orNull(form.application_url),
    location: orNull(form.location),
    remote_mode: form.remote_mode || null,
    application_deadline: orNull(form.application_deadline),
    start_date: orNull(form.start_date),
    end_date: orNull(form.end_date),
    requirements_assessment_status: form.requirements_assessment_status,
    requirements: form.requirements.map(toRequirementInput),
  }
}

/** Create (/opportunities/new) or edit (/opportunities/:id/edit) a manual opportunity. */
export function OpportunityFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [form, setForm] = useState<Form | null>(id ? null : emptyForm)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [issues, setIssues] = useState<FieldIssue[]>([])

  useEffect(() => {
    if (!id) return
    // Ignore responses that arrive after unmount or a re-run (e.g. StrictMode runs effects
    // twice), so a late response can't overwrite what the user already typed.
    let active = true
    api
      .getOpportunity(id)
      .then((o) => active && setForm(toForm(o)))
      .catch(
        (caught: unknown) =>
          active &&
          setLoadError(caught instanceof Error ? caught.message : 'Could not load it.'),
      )
    return () => {
      active = false
    }
  }, [id])

  if (loadError) return <ErrorMessage>{loadError}</ErrorMessage>
  if (!form) return <p role="status">Loading…</p>
  const current = form

  const text = (name: TextField, label: string, type = 'text', required = false) => {
    const fieldError = issueFor(issues, name)
    return (
      <Field
        id={name}
        label={required ? `${label} (required)` : label}
        error={fieldError}
      >
        <input
          id={name}
          type={type}
          required={required}
          value={current[name]}
          onChange={(event) => setForm({ ...current, [name]: event.target.value })}
          {...describedBy(name, undefined, fieldError)}
          className={inputClass}
        />
      </Field>
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setIssues([])
    try {
      const body = toInput(current)
      const saved = id
        ? await api.updateOpportunity(id, body)
        : await api.createOpportunity(body)
      navigate(`/opportunities/${saved.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save.')
      if (caught instanceof ApiError) setIssues(caught.issues)
      setSaving(false)
    }
  }

  const requirementIssues = issueFor(issues, 'requirements')
  const otherIssues = issues.filter((i) => i.field === null)
  return (
    <form onSubmit={handleSubmit} className="space-y-6" noValidate>
      <h1 className="text-2xl font-semibold">
        {id ? 'Edit opportunity' : 'Add opportunity'}
      </h1>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Details</legend>
        {text('title', 'Title', 'text', true)}
        {text('organization', 'Organization', 'text', true)}
        <Field id="opportunity_type" label="Type">
          <select
            id="opportunity_type"
            value={current.opportunity_type}
            onChange={(e) =>
              setForm({ ...current, opportunity_type: e.target.value as OpportunityType })
            }
            className={inputClass}
          >
            {opportunityTypes.map((type) => (
              <option key={type} value={type}>
                {opportunityTypeLabels[type]}
              </option>
            ))}
          </select>
        </Field>
        <Field
          id="description"
          label="Description"
          error={issueFor(issues, 'description')}
        >
          <textarea
            id="description"
            rows={4}
            value={current.description}
            onChange={(e) => setForm({ ...current, description: e.target.value })}
            className={inputClass}
          />
        </Field>
        {text('application_url', 'Application URL', 'url')}
        {text('location', 'Location')}
        <Field id="remote_mode" label="Remote mode">
          <select
            id="remote_mode"
            value={current.remote_mode}
            onChange={(e) =>
              setForm({ ...current, remote_mode: e.target.value as RemoteMode })
            }
            className={inputClass}
          >
            <option value="">Not stated</option>
            {remoteModes.map((mode) => (
              <option key={mode} value={mode}>
                {remoteModeLabels[mode]}
              </option>
            ))}
          </select>
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          {text('application_deadline', 'Application deadline', 'date')}
          {text('start_date', 'Start date', 'date')}
          {text('end_date', 'End date', 'date')}
        </div>
      </fieldset>

      <fieldset className={fieldsetClass}>
        <legend className={legendClass}>Hard requirements</legend>
        <p className="text-sm text-slate-600">
          Record each eligibility requirement from the posting. Age and education are
          checked against your expected status on the date they apply.
        </p>
        <RequirementsEditor
          rows={current.requirements}
          onChange={(requirements) => setForm({ ...current, requirements })}
        />
        {requirementIssues && <ErrorMessage>{requirementIssues}</ErrorMessage>}
        <fieldset>
          <legend className="text-sm font-medium">How complete is this list?</legend>
          {assessmentStatuses.map((status) => (
            <label key={status} className="mt-1 flex items-start gap-2">
              <input
                type="radio"
                name="requirements_assessment_status"
                value={status}
                checked={current.requirements_assessment_status === status}
                onChange={() =>
                  setForm({ ...current, requirements_assessment_status: status })
                }
                className="mt-1"
              />
              <span>
                <span className="font-medium">{assessmentLabels[status]}</span>
                <span className="block text-sm text-slate-600">
                  {assessmentDescriptions[status]}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
      </fieldset>

      {otherIssues.map((issue) => (
        <ErrorMessage key={issue.message}>{issue.message}</ErrorMessage>
      ))}
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <div className="flex gap-3">
        <button type="submit" disabled={saving} className={buttonClass}>
          {saving ? 'Saving…' : 'Save opportunity'}
        </button>
        <Link
          to={id ? `/opportunities/${id}` : '/opportunities'}
          className="self-center underline"
        >
          Cancel
        </Link>
      </div>
    </form>
  )
}
