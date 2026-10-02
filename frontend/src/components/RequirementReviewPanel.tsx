import { useEffect, useState } from 'react'
import { api } from '../api/client'
import {
  assessmentStatuses,
  type AssessmentStatus,
  type CandidateAcceptInput,
  type RequirementCandidate,
  type RequirementReviewInput,
  type RequirementReviewResponse,
} from '../api/schemas'
import {
  appliesAtLabels,
  assessmentDescriptions,
  assessmentLabels,
  requirementTypeLabels,
} from '../lib/labels'
import {
  describeValue,
  toCandidateEdit,
  toRow,
  type RequirementRow,
} from '../lib/requirements'
import { buttonClass, secondaryButtonClass } from '../lib/styles'
import { RequirementValueFields } from './RequirementsEditor'
import { ErrorMessage } from './ui'

// Owner review of deterministic requirement candidates (ADR-012 §7). Candidates never affect
// eligibility until accepted into a canonical requirement, so staging here is purely local
// state: nothing changes on the server until "Apply changes" sends one batch.

type Choice =
  | { action: 'accept'; edited: false }
  | { action: 'accept'; edited: true; row: RequirementRow }
  | { action: 'reject' }

type AssessmentChoice = AssessmentStatus | 'no_change'

function failureMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

/** A short summary of a candidate's type and value, for accessible names like
 * "Accept minimum age 16". Never raw JSON. */
function candidateLabel(candidate: RequirementCandidate): string {
  const type = requirementTypeLabels[candidate.requirement_type].toLowerCase()
  const value = candidate.value
  if (typeof value.years === 'number') return `${type} ${value.years}`
  if (Array.isArray(value.levels) && value.levels.length)
    return `${type} (${(value.levels as string[]).join(', ')})`
  if (Array.isArray(value.countries) && value.countries.length)
    return `${type} (${(value.countries as string[]).join(', ')})`
  if (typeof value.description === 'string' && value.description)
    return `${type}: ${value.description}`
  return type
}

/** Disambiguates candidateLabel() across one opportunity's candidates, so two candidates that
 * summarize the same (e.g. two "other" requirements) still get unique accessible names. */
function uniqueLabels(candidates: RequirementCandidate[]): Map<string, string> {
  const seen = new Map<string, number>()
  const labels = new Map<string, string>()
  for (const candidate of candidates) {
    const base = candidateLabel(candidate)
    const count = (seen.get(base) ?? 0) + 1
    seen.set(base, count)
    labels.set(candidate.id, count === 1 ? base : `${base} #${count}`)
  }
  return labels
}

function buildBody(
  staged: Record<string, Choice>,
  assessmentChoice: AssessmentChoice,
): RequirementReviewInput {
  const accept: CandidateAcceptInput[] = []
  const reject: string[] = []
  for (const [id, choice] of Object.entries(staged)) {
    if (choice.action === 'reject') reject.push(id)
    else if (choice.edited) accept.push({ id, ...toCandidateEdit(choice.row) })
    else accept.push({ id })
  }
  const body: RequirementReviewInput = { accept, reject }
  if (assessmentChoice !== 'no_change') body.assessment_status = assessmentChoice
  return body
}

interface Actions {
  stageAccept: (id: string) => void
  stageReject: (id: string) => void
  unstage: (id: string) => void
  startEdit: (candidate: RequirementCandidate) => void
  updateEditRow: (id: string, changes: Partial<RequirementRow>) => void
}

function CandidateItem({
  candidate,
  label,
  stage,
  actions,
}: {
  candidate: RequirementCandidate
  label: string
  stage: Choice | undefined
  actions: Actions
}) {
  const acceptedPlain = stage?.action === 'accept' && !stage.edited
  const editing = stage?.action === 'accept' && stage.edited
  const rejecting = stage?.action === 'reject'
  return (
    <li className="space-y-2 rounded border border-slate-100 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">
          {requirementTypeLabels[candidate.requirement_type]}
        </span>
        <span>{describeValue(candidate.value)}</span>
        <span className="text-sm text-slate-600">
          ({appliesAtLabels[candidate.applies_at].toLowerCase()})
        </span>
        {!candidate.is_current && (
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-700">
            No longer in posting
          </span>
        )}
      </div>
      {candidate.source_text && (
        <p className="text-sm italic text-slate-600">
          &ldquo;{candidate.source_text}&rdquo;
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() =>
            acceptedPlain
              ? actions.unstage(candidate.id)
              : actions.stageAccept(candidate.id)
          }
          className={secondaryButtonClass}
        >
          {acceptedPlain ? `Cancel accept ${label}` : `Accept ${label}`}
        </button>
        <button
          type="button"
          onClick={() =>
            editing ? actions.unstage(candidate.id) : actions.startEdit(candidate)
          }
          className={secondaryButtonClass}
        >
          {editing ? `Cancel edit ${label}` : `Edit ${label}`}
        </button>
        <button
          type="button"
          onClick={() =>
            rejecting ? actions.unstage(candidate.id) : actions.stageReject(candidate.id)
          }
          className={secondaryButtonClass}
        >
          {rejecting ? `Cancel reject ${label}` : `Reject ${label}`}
        </button>
      </div>
      {editing && (
        <fieldset className="space-y-2 rounded border border-slate-200 p-2">
          <legend className="px-1 text-sm font-medium">Edit {label}</legend>
          <RequirementValueFields
            row={stage.row}
            onChange={(changes) => actions.updateEditRow(candidate.id, changes)}
            idPrefix={`cand-${candidate.id}`}
          />
        </fieldset>
      )}
    </li>
  )
}

function Section({
  title,
  candidates,
  emptyText,
  labels,
  staged,
  actions,
}: {
  title: string
  candidates: RequirementCandidate[]
  emptyText: string
  labels: Map<string, string>
  staged: Record<string, Choice>
  actions: Actions
}) {
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="font-medium">{title}</h3>
      {candidates.length === 0 ? (
        <p className="text-sm text-slate-600">{emptyText}</p>
      ) : (
        <ul className="space-y-2">
          {candidates.map((candidate) => (
            <CandidateItem
              key={candidate.id}
              candidate={candidate}
              label={
                labels.get(candidate.id) ??
                requirementTypeLabels[candidate.requirement_type]
              }
              stage={staged[candidate.id]}
              actions={actions}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

export function RequirementReviewPanel({
  opportunityId,
  onReviewed,
}: {
  opportunityId: string
  /** Called after a successful review batch, so the page can reload the opportunity (the
   * Eligibility panel and pending-suggestion counts read from it, not from this panel). */
  onReviewed: () => void
}) {
  const [review, setReview] = useState<RequirementReviewResponse | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [staged, setStaged] = useState<Record<string, Choice>>({})
  const [assessmentChoice, setAssessmentChoice] = useState<AssessmentChoice>('no_change')
  const [busy, setBusy] = useState<'refresh' | 'apply' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    // The caller keys this component by opportunityId (it remounts on a new opportunity), so
    // this always starts from this component's own initial state.
    let active = true
    api
      .getRequirementReview(opportunityId)
      .then((r) => active && setReview(r))
      .catch(
        (caught: unknown) =>
          active &&
          setLoadError(failureMessage(caught, 'Could not load requirement suggestions.')),
      )
    return () => {
      active = false
    }
  }, [opportunityId])

  const actions: Actions = {
    stageAccept: (id) =>
      setStaged((prev) => ({ ...prev, [id]: { action: 'accept', edited: false } })),
    stageReject: (id) => setStaged((prev) => ({ ...prev, [id]: { action: 'reject' } })),
    unstage: (id) =>
      setStaged((prev) => {
        const next = { ...prev }
        delete next[id]
        return next
      }),
    startEdit: (candidate) =>
      setStaged((prev) => ({
        ...prev,
        [candidate.id]: { action: 'accept', edited: true, row: toRow(candidate) },
      })),
    updateEditRow: (id, changes) =>
      setStaged((prev) => {
        const current = prev[id]
        if (!current || current.action !== 'accept' || !current.edited) return prev
        return { ...prev, [id]: { ...current, row: { ...current.row, ...changes } } }
      }),
  }

  async function refresh() {
    setBusy('refresh')
    setActionError(null)
    try {
      setReview(await api.refreshRequirementReview(opportunityId))
      setStaged({})
    } catch (caught) {
      setActionError(failureMessage(caught, 'Could not refresh suggestions.'))
    } finally {
      setBusy(null)
    }
  }

  async function apply() {
    setBusy('apply')
    setActionError(null)
    try {
      const result = await api.reviewRequirements(
        opportunityId,
        buildBody(staged, assessmentChoice),
      )
      setReview(result.review)
      setStaged({})
      setAssessmentChoice('no_change')
      onReviewed()
    } catch (caught) {
      setActionError(failureMessage(caught, 'Could not save the review.'))
    } finally {
      setBusy(null)
    }
  }

  if (loadError)
    return (
      <section aria-label="Requirement Review" className="rounded border p-4">
        <h2 className="text-lg font-semibold">Requirement Review</h2>
        <ErrorMessage>{loadError}</ErrorMessage>
      </section>
    )
  if (!review)
    return (
      <section aria-label="Requirement Review" className="rounded border p-4">
        <h2 className="text-lg font-semibold">Requirement Review</h2>
        <p role="status">Loading requirement suggestions…</p>
      </section>
    )

  // An accepted suggestion shows (and edits from) the canonical requirement the owner accepted,
  // which may be an edited version of the original proposal.
  const canonical = new Map(review.requirements.map((r) => [r.id, r]))
  const candidates = review.candidates.map((c) => {
    const linked = c.accepted_requirement_id
      ? canonical.get(c.accepted_requirement_id)
      : undefined
    return linked
      ? {
          ...c,
          value: linked.value,
          applies_at: linked.applies_at,
          reference_date: linked.reference_date,
        }
      : c
  })
  const labels = uniqueLabels(candidates)
  const pending = candidates.filter((c) => c.review_state === 'pending')
  const accepted = candidates.filter((c) => c.review_state === 'accepted')
  const rejected = candidates.filter((c) => c.review_state === 'rejected')
  const stagedCount = Object.keys(staged).length
  const applyDisabled =
    busy !== null || (stagedCount === 0 && assessmentChoice === 'no_change')

  return (
    <section aria-label="Requirement Review" className="space-y-4 rounded border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Requirement Review</h2>
        <button
          type="button"
          onClick={refresh}
          disabled={busy !== null}
          className={secondaryButtonClass}
        >
          {busy === 'refresh' ? 'Refreshing…' : 'Refresh suggestions'}
        </button>
      </div>
      <p className="text-sm text-slate-600">
        Suggestions do not affect eligibility until you accept them.
      </p>
      <p>
        <span className="text-slate-500">Assessment: </span>
        {assessmentLabels[review.requirements_assessment_status]}
      </p>
      {review.requirements_stale_since && (
        <p className="rounded border border-amber-200 bg-amber-50 p-3 text-amber-900">
          Posting changed since requirement review. Review requirements again.
        </p>
      )}
      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      <Section
        title="Pending suggestions"
        candidates={pending}
        emptyText="No pending suggestions."
        labels={labels}
        staged={staged}
        actions={actions}
      />
      <Section
        title="Accepted"
        candidates={accepted}
        emptyText="Nothing accepted yet."
        labels={labels}
        staged={staged}
        actions={actions}
      />
      <Section
        title="Rejected"
        candidates={rejected}
        emptyText="Nothing rejected."
        labels={labels}
        staged={staged}
        actions={actions}
      />

      <fieldset className="rounded border border-slate-200 p-3">
        <legend className="px-1 text-sm font-medium">
          How complete is this requirement list?
        </legend>
        <p className="text-sm text-slate-600">
          Marking it complete asserts every hard requirement in this posting is
          represented above and in Requirements, not just the ones a suggestion found.
        </p>
        <label className="mt-2 flex items-start gap-2">
          <input
            type="radio"
            name="requirement-review-assessment"
            value="no_change"
            checked={assessmentChoice === 'no_change'}
            onChange={() => setAssessmentChoice('no_change')}
            className="mt-1"
          />
          <span className="font-medium">
            Keep current ({assessmentLabels[review.requirements_assessment_status]})
          </span>
        </label>
        {assessmentStatuses.map((status) => (
          <label key={status} className="mt-1 flex items-start gap-2">
            <input
              type="radio"
              name="requirement-review-assessment"
              value={status}
              checked={assessmentChoice === status}
              onChange={() => setAssessmentChoice(status)}
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

      <button
        type="button"
        onClick={apply}
        disabled={applyDisabled}
        className={buttonClass}
      >
        {busy === 'apply'
          ? 'Saving…'
          : `Apply changes${stagedCount ? ` (${stagedCount})` : ''}`}
      </button>
    </section>
  )
}
