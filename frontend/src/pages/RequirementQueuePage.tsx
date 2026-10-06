import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ApiError, api } from '../api/client'
import {
  requirementTypes,
  sourceKinds,
  type QueueItem,
  type QueuePage,
  type QueueQuery,
  type RequirementReviewInput,
  type RequirementType,
  type SourceKind,
} from '../api/schemas'
import { FreshnessBadge } from '../components/FreshnessBadge'
import { RequirementValueFields } from '../components/RequirementsEditor'
import { ErrorMessage, Field } from '../components/ui'
import {
  appliesAtLabels,
  formatDay,
  requirementTypeLabels,
  sourceKindLabels,
} from '../lib/labels'
import {
  describeValue,
  toCandidateEdit,
  toRow,
  type RequirementRow,
} from '../lib/requirements'
import {
  moveCursor,
  pruneSelection,
  shortcutFor,
  shortcutHints,
  type ShortcutAction,
} from '../lib/reviewQueue'
import {
  buttonClass,
  dangerButtonClass,
  inputClass,
  secondaryButtonClass,
} from '../lib/styles'

// ADR-024: one queue of pending requirement suggestions across opportunities. The owner stays
// authoritative: every accept/reject is an explicit action on one suggestion (through the same
// atomic review endpoint as the opportunity page), and the only bulk action is "Reject selected".

const PAGE_SIZE = 50
const MAX_PAGE_SIZE = 100

interface Draft {
  type: RequirementType | ''
  version: string
  organization: string
  source: SourceKind | ''
  changed: boolean
}
const emptyDraft: Draft = {
  type: '',
  version: '',
  organization: '',
  source: '',
  changed: false,
}

function toQuery(draft: Draft, limit: number): QueueQuery {
  return {
    requirement_type: draft.type || undefined,
    extractor_version: draft.version || undefined,
    organization: draft.organization.trim() || undefined,
    source_kind: draft.source || undefined,
    posting_changed: draft.changed,
    limit,
  }
}

function failureMessage(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError && caught.issues.length)
    return caught.issues.map((i) => i.message).join(' ')
  return caught instanceof Error ? caught.message : fallback
}

function summaryLabel(item: QueueItem): string {
  const c = item.candidate
  return `${requirementTypeLabels[c.requirement_type]} ${describeValue(c.value)} on ${item.opportunity.title}`
}

function Card({
  item,
  position,
  count,
  skipped,
  duplicateText,
  editRow,
  busy,
  onEditRow,
  onAction,
  onSaveEdit,
  onCancelEdit,
}: {
  item: QueueItem
  position: number
  count: number
  skipped: boolean
  duplicateText: string | null
  editRow: RequirementRow | null
  busy: boolean
  onEditRow: (changes: Partial<RequirementRow>) => void
  onAction: (action: ShortcutAction) => void
  onSaveEdit: () => void
  onCancelEdit: () => void
}) {
  const { candidate, opportunity } = item
  return (
    <section
      aria-label="Current suggestion"
      className="min-w-0 space-y-3 break-words rounded border border-slate-300 p-4"
    >
      <p className="text-sm text-slate-600">
        Suggestion {position} of {count} loaded{skipped ? ' · skipped' : ''}
      </p>
      <div>
        <h2 className="text-lg font-semibold">
          <Link
            to={`/opportunities/${opportunity.id}`}
            className="text-blue-800 underline"
          >
            {opportunity.title}
          </Link>
        </h2>
        <p className="flex flex-wrap items-center gap-2 text-slate-700">
          <span>{opportunity.organization}</span>
          <FreshnessBadge
            o={{
              freshness: opportunity.freshness,
              freshness_checked_at: opportunity.freshness_checked_at,
              program_last_verified: null,
              verify_by: null,
            }}
          />
          <span className="text-sm text-slate-600">
            First found {formatDay(opportunity.first_seen_at)}
            {opportunity.source_names.length > 0 &&
              ` · ${opportunity.source_names.join(', ')}`}
          </span>
        </p>
        {opportunity.requirements_stale_since && (
          <p className="mt-1 text-sm text-amber-900">
            Posting changed since requirement review.
          </p>
        )}
      </div>

      <blockquote className="rounded border-l-4 border-amber-400 bg-slate-50 p-3">
        <p className="text-sm text-slate-600">From the posting</p>
        <p>
          <mark className="bg-amber-100 px-0.5">{candidate.source_text}</mark>
        </p>
      </blockquote>

      <div>
        <p className="text-sm text-slate-600">The suggestion reads this as</p>
        <p className="font-medium">
          {requirementTypeLabels[candidate.requirement_type]}:{' '}
          {describeValue(candidate.value)}{' '}
          <span className="text-sm font-normal text-slate-600">
            ({appliesAtLabels[candidate.applies_at].toLowerCase()})
          </span>
        </p>
        <p className="text-xs text-slate-500">
          {candidate.extractor_name} v{candidate.extractor_version}. It does not affect
          eligibility until you accept it.
        </p>
      </div>

      {duplicateText && (
        <p
          role="status"
          className="rounded border border-amber-300 bg-amber-50 p-3 text-amber-900"
        >
          {duplicateText}
        </p>
      )}

      <div>
        <h3 className="text-sm font-medium">
          Requirements already on this opportunity ({item.existing_requirements.length})
        </h3>
        {item.existing_requirements.length === 0 ? (
          <p className="text-sm text-slate-600">None yet.</p>
        ) : (
          <ul className="list-disc pl-5 text-sm">
            {item.existing_requirements.map((r) => (
              <li key={r.id}>
                {requirementTypeLabels[r.requirement_type]}: {describeValue(r.value)} (
                {appliesAtLabels[r.applies_at].toLowerCase()})
                {r.id === item.duplicate_of && ' · same as this suggestion'}
              </li>
            ))}
          </ul>
        )}
      </div>

      {editRow ? (
        <fieldset className="space-y-2 rounded border border-slate-200 p-3">
          <legend className="px-1 text-sm font-medium">Edit before accepting</legend>
          <RequirementValueFields
            row={editRow}
            onChange={onEditRow}
            idPrefix="queue-edit"
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onSaveEdit}
              disabled={busy}
              className={buttonClass}
            >
              Save edit and accept
            </button>
            <button
              type="button"
              onClick={onCancelEdit}
              disabled={busy}
              className={secondaryButtonClass}
            >
              Cancel edit
            </button>
          </div>
        </fieldset>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onAction('accept')}
            disabled={busy}
            className={buttonClass}
          >
            Accept
          </button>
          <button
            type="button"
            onClick={() => onAction('edit')}
            disabled={busy}
            className={secondaryButtonClass}
          >
            Edit + Accept
          </button>
          <button
            type="button"
            onClick={() => onAction('reject')}
            disabled={busy}
            className={dangerButtonClass}
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => onAction('skip')}
            disabled={busy}
            className={secondaryButtonClass}
          >
            Skip
          </button>
          <button
            type="button"
            onClick={() => onAction('previous')}
            disabled={busy || position <= 1}
            className={secondaryButtonClass}
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => onAction('next')}
            disabled={busy || position >= count}
            className={secondaryButtonClass}
          >
            Next
          </button>
        </div>
      )}
    </section>
  )
}

export function RequirementQueuePage() {
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [applied, setApplied] = useState<Draft>(emptyDraft)
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [page, setPage] = useState<QueuePage | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [cursor, setCursor] = useState(0)
  const [skipped, setSkipped] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const [editRow, setEditRow] = useState<RequirementRow | null>(null)
  const [busy, setBusy] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  // One read per (filters, page size, reload). A reload after each decision keeps the counts
  // and the list exact; the decided suggestion has left the queue, so the cursor index now
  // points at the next one.
  useEffect(() => {
    let active = true
    api
      .getRequirementQueue(toQuery(applied, limit))
      .then((result) => {
        if (!active) return
        setPage(result)
        setLoadError(null)
        setCursor((c) => moveCursor(c, 0, result.items.length))
        setSelected((s) =>
          pruneSelection(
            s,
            result.items.map((i) => i.candidate.id),
          ),
        )
      })
      .catch(
        (caught: unknown) =>
          active &&
          setLoadError(failureMessage(caught, 'Could not load the review queue.')),
      )
    return () => {
      active = false
    }
  }, [applied, limit, reloadKey])

  const items = page?.items ?? []
  const item: QueueItem | undefined = items[cursor]
  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  const decide = useCallback(
    async (body: RequirementReviewInput, done: string) => {
      if (!item) return
      setBusy(true)
      setActionError(null)
      setNotice(null)
      try {
        await api.reviewRequirements(item.opportunity.id, body)
        setEditRow(null)
        setNotice(done)
        reload()
      } catch (caught) {
        setActionError(failureMessage(caught, 'Could not save the review.'))
      } finally {
        setBusy(false)
      }
    },
    [item, reload],
  )

  const act = useCallback(
    (action: ShortcutAction) => {
      if (!item || busy) return
      const id = item.candidate.id
      if (action === 'accept') void decide({ accept: [{ id }], reject: [] }, 'Accepted.')
      else if (action === 'reject') void decide({ accept: [], reject: [id] }, 'Rejected.')
      else if (action === 'edit') setEditRow(toRow(item.candidate))
      else {
        if (action === 'skip') setSkipped((s) => new Set(s).add(id))
        setCursor((c) => moveCursor(c, action === 'previous' ? -1 : 1, items.length))
        setActionError(null)
        setNotice(null)
      }
    },
    [item, busy, decide, items.length],
  )

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (editRow) {
        if (event.key === 'Escape') setEditRow(null)
        return
      }
      const action = shortcutFor(event)
      if (!action) return
      event.preventDefault()
      act(action)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [act, editRow])

  async function rejectSelected() {
    setBusy(true)
    setActionError(null)
    setNotice(null)
    try {
      const result = await api.rejectCandidatesBatch([...selected])
      setSelected(new Set())
      setNotice(
        `Rejected ${result.rejected} suggestion${result.rejected === 1 ? '' : 's'}.`,
      )
      reload()
    } catch (caught) {
      setActionError(failureMessage(caught, 'Could not reject the selection.'))
    } finally {
      setConfirming(false)
      setBusy(false)
    }
  }

  function applyFilters(next: Draft) {
    setApplied(next)
    setLimit(PAGE_SIZE)
    setCursor(0)
    setSelected(new Set())
    setConfirming(false)
    setEditRow(null)
  }

  function toggle(id: string) {
    setConfirming(false)
    setSelected((s) => {
      const next = new Set(s)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  if (loadError && !page)
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Review</h1>
        <ErrorMessage>{loadError}</ErrorMessage>
        <button type="button" onClick={reload} className={secondaryButtonClass}>
          Try again
        </button>
      </div>
    )
  if (!page)
    return (
      <p role="status" aria-live="polite">
        Loading…
      </p>
    )

  const { summary } = page
  const duplicateText =
    item?.duplicate_of != null
      ? 'This opportunity already has a requirement that means the same thing. ' +
        'Accepting links this suggestion to it; no duplicate is created.'
      : null

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Review</h1>
      <p className="text-slate-600">
        Pending requirement suggestions across all open opportunities. Nothing here
        affects eligibility until you accept it.
      </p>

      <section aria-label="Progress" className="space-y-1 rounded border p-4">
        <p>
          <strong>{summary.pending_total}</strong> pending in total ·{' '}
          <strong>{page.total}</strong> in this view
        </p>
        <p className="text-sm text-slate-700">
          Reviewed today (UTC): {summary.accepted_today} accepted,{' '}
          {summary.rejected_today} rejected
        </p>
        {summary.by_type.length > 0 && (
          <ul className="flex flex-wrap gap-x-4 text-sm text-slate-700">
            {summary.by_type.map((c) => (
              <li key={c.requirement_type}>
                {requirementTypeLabels[c.requirement_type]}: {c.count}
              </li>
            ))}
          </ul>
        )}
      </section>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          applyFilters(draft)
        }}
        aria-label="Filters"
        className="grid gap-3 rounded border p-4 sm:grid-cols-2"
      >
        <Field id="queue-type" label="Category">
          <select
            id="queue-type"
            value={draft.type}
            onChange={(e) =>
              setDraft({ ...draft, type: e.target.value as RequirementType | '' })
            }
            className={inputClass}
          >
            <option value="">All categories</option>
            {requirementTypes.map((t) => (
              <option key={t} value={t}>
                {requirementTypeLabels[t]}
              </option>
            ))}
          </select>
        </Field>
        <Field id="queue-version" label="Extractor version">
          <select
            id="queue-version"
            value={draft.version}
            onChange={(e) => setDraft({ ...draft, version: e.target.value })}
            className={inputClass}
          >
            <option value="">All versions</option>
            {summary.extractor_versions.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field id="queue-source" label="Source type">
          <select
            id="queue-source"
            value={draft.source}
            onChange={(e) =>
              setDraft({ ...draft, source: e.target.value as SourceKind | '' })
            }
            className={inputClass}
          >
            <option value="">All sources</option>
            {sourceKinds.map((k) => (
              <option key={k} value={k}>
                {sourceKindLabels[k]}
              </option>
            ))}
          </select>
        </Field>
        <Field id="queue-org" label="Organization contains">
          <input
            id="queue-org"
            type="text"
            maxLength={200}
            value={draft.organization}
            onChange={(e) => setDraft({ ...draft, organization: e.target.value })}
            className={inputClass}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.changed}
            onChange={(e) => setDraft({ ...draft, changed: e.target.checked })}
          />
          Only postings that changed since review
        </label>
        <div className="flex gap-2 sm:justify-end">
          <button type="submit" className={buttonClass}>
            Apply filters
          </button>
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => {
              setDraft(emptyDraft)
              applyFilters(emptyDraft)
            }}
          >
            Clear
          </button>
        </div>
      </form>

      <p className="text-sm text-slate-700" aria-label="Keyboard shortcuts">
        Shortcuts:{' '}
        {shortcutHints.map((h) => (
          <span key={h.key} className="mr-3 inline-block whitespace-nowrap">
            <kbd className="rounded border border-slate-300 bg-slate-50 px-1">
              {h.key}
            </kbd>{' '}
            {h.label}
          </span>
        ))}
        (off while typing in a field)
      </p>

      <div aria-live="polite">
        {notice && (
          <p role="status" className="rounded border border-green-200 bg-green-50 p-3">
            {notice}
          </p>
        )}
      </div>
      {loadError && <ErrorMessage>{loadError}</ErrorMessage>}
      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {item ? (
        <Card
          key={item.candidate.id}
          item={item}
          position={cursor + 1}
          count={items.length}
          skipped={skipped.has(item.candidate.id)}
          duplicateText={duplicateText}
          editRow={editRow}
          busy={busy}
          onEditRow={(changes) => setEditRow((r) => (r ? { ...r, ...changes } : r))}
          onAction={act}
          onCancelEdit={() => setEditRow(null)}
          onSaveEdit={() =>
            editRow &&
            void decide(
              {
                accept: [{ id: item.candidate.id, ...toCandidateEdit(editRow) }],
                reject: [],
              },
              'Accepted with your edit.',
            )
          }
        />
      ) : (
        <p className="rounded border p-4 text-slate-700">
          {summary.pending_total === 0
            ? 'Nothing to review. New suggestions appear after the next sync.'
            : 'No suggestions match these filters.'}
        </p>
      )}

      {items.length > 0 && (
        <section aria-label="Loaded suggestions" className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">
              Loaded suggestions ({items.length} of {page.total})
            </h2>
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={() => {
                setConfirming(false)
                setSelected(new Set(items.map((i) => i.candidate.id)))
              }}
            >
              Select all loaded
            </button>
            <button
              type="button"
              className={secondaryButtonClass}
              disabled={selected.size === 0}
              onClick={() => {
                setConfirming(false)
                setSelected(new Set())
              }}
            >
              Clear selection
            </button>
            <button
              type="button"
              className={dangerButtonClass}
              disabled={selected.size === 0 || busy}
              onClick={() => setConfirming(true)}
            >
              Reject selected ({selected.size})
            </button>
          </div>
          {confirming && selected.size > 0 && (
            <div
              role="group"
              aria-label="Confirm batch reject"
              className="space-y-2 rounded border border-red-300 bg-red-50 p-3"
            >
              <p>
                Reject {selected.size} suggestion{selected.size === 1 ? '' : 's'}?
                Rejected suggestions are not proposed again. Nothing is accepted.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={rejectSelected}
                  disabled={busy}
                  className={dangerButtonClass}
                >
                  Confirm reject
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                  className={secondaryButtonClass}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
          <ul className="divide-y rounded border">
            {items.map((i, index) => (
              <li
                key={i.candidate.id}
                className={`flex items-start gap-2 p-2 ${index === cursor ? 'bg-slate-100' : ''}`}
              >
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={selected.has(i.candidate.id)}
                  onChange={() => toggle(i.candidate.id)}
                  aria-label={`Select ${summaryLabel(i)}`}
                />
                <button
                  type="button"
                  onClick={() => {
                    setEditRow(null)
                    setCursor(index)
                  }}
                  className="min-w-0 break-words text-left"
                  aria-current={index === cursor ? 'true' : undefined}
                >
                  <span className="font-medium">
                    {requirementTypeLabels[i.candidate.requirement_type]}:{' '}
                    {describeValue(i.candidate.value)}
                  </span>
                  <span className="block text-sm text-slate-600">
                    {i.opportunity.title} · {i.opportunity.organization}
                    {i.duplicate_of ? ' · already a requirement' : ''}
                    {skipped.has(i.candidate.id) ? ' · skipped' : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {page.total > items.length && limit < MAX_PAGE_SIZE && (
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={() => setLimit(MAX_PAGE_SIZE)}
            >
              Load more
            </button>
          )}
        </section>
      )}
    </div>
  )
}
