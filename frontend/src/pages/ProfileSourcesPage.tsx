import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { api } from '../api/client'
import {
  factCategories,
  type FactReviewInput,
  type ImportedFact,
  type ProfileSourceDetail,
  type ProfileSourceReviewInput,
  type ProfileSourceSummary,
  type ReviewState,
} from '../api/schemas'
import { ProfileTabs } from '../components/ProfileTabs'
import { ErrorMessage, Field, SuccessMessage } from '../components/ui'
import {
  buttonClass,
  dangerButtonClass,
  fieldsetClass,
  inputClass,
  secondaryButtonClass,
} from '../lib/styles'

// ADR-011: imported facts never affect matching until accepted; only skill/course/project/
// research feed the Match Profile. Everything else is kept for reference only.

const MAX_BYTES = 2 * 1024 * 1024

const categoryLabels: Record<(typeof factCategories)[number], string> = {
  skill: 'Skills',
  course: 'Courses',
  project: 'Projects',
  research: 'Research',
  experience: 'Experience',
  activity: 'Activities',
  award: 'Awards',
  education: 'Education',
}

/** No description is ever accepted for these categories (ADR-011 §8). */
function hasDescription(category: ImportedFact['category']): boolean {
  return category !== 'skill' && category !== 'course'
}

interface Staged {
  action: 'accept' | 'reject'
  name: string
  description: string
}

function summaryOf(detail: ProfileSourceDetail): ProfileSourceSummary {
  const {
    id,
    kind,
    original_filename,
    content_type,
    byte_size,
    parser_name,
    parser_version,
    ingested_at,
    pending_count,
    accepted_count,
    rejected_count,
  } = detail
  return {
    id,
    kind,
    original_filename,
    content_type,
    byte_size,
    parser_name,
    parser_version,
    ingested_at,
    pending_count,
    accepted_count,
    rejected_count,
  }
}

function buildReviewBody(
  facts: ImportedFact[],
  staged: Record<string, Staged>,
): ProfileSourceReviewInput {
  const accept: FactReviewInput[] = []
  const reject: string[] = []
  for (const fact of facts) {
    const stage = staged[fact.id]
    if (!stage) continue
    if (stage.action === 'reject') {
      reject.push(fact.id)
    } else {
      const entry: FactReviewInput = { id: fact.id, name: stage.name.trim() }
      if (hasDescription(fact.category))
        entry.description = stage.description.trim() || null
      accept.push(entry)
    }
  }
  return { accept, reject }
}

function rescoreMessage(
  catalogPass: boolean,
  evaluated: number,
  unchanged: number,
): string {
  if (!catalogPass) return 'Saved. Matching unchanged.'
  return `Scoring refreshed: ${evaluated} opportunit${evaluated === 1 ? 'y' : 'ies'} re-scored, ${unchanged} unchanged.`
}

function Badge({ children, tone = 'slate' }: { children: ReactNode; tone?: string }) {
  const tones: Record<string, string> = {
    slate: 'bg-slate-100 text-slate-700',
    green: 'bg-green-100 text-green-800',
    red: 'bg-red-100 text-red-800',
    amber: 'bg-amber-100 text-amber-800',
  }
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone] ?? tones.slate}`}
    >
      {children}
    </span>
  )
}

function StatusBadge({ state }: { state: ReviewState }) {
  if (state === 'accepted') return <Badge tone="green">Verified</Badge>
  if (state === 'rejected') return <Badge tone="red">Rejected</Badge>
  return <Badge tone="amber">Pending</Badge>
}

function failureMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

export function ProfileSourcesPage() {
  const [sources, setSources] = useState<ProfileSourceSummary[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)

  const [actionError, setActionError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const [openId, setOpenId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProfileSourceDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [staged, setStaged] = useState<Record<string, Staged>>({})
  const [saving, setSaving] = useState(false)
  const [reviewMessage, setReviewMessage] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api
      .listProfileSources()
      .then((list) => active && setSources(list))
      .catch(
        (caught: unknown) =>
          active &&
          setLoadError(failureMessage(caught, 'Could not load your imported files.')),
      )
    return () => {
      active = false
    }
  }, [])

  function resetPanel() {
    setDetail(null)
    setDetailError(null)
    setStaged({})
    setReviewMessage(null)
    setReviewError(null)
  }

  function toggleOpen(id: string) {
    if (openId === id) {
      setOpenId(null)
      resetPanel()
      return
    }
    setOpenId(id)
    resetPanel()
    api
      .getProfileSource(id)
      .then(setDetail)
      .catch((caught: unknown) =>
        setDetailError(failureMessage(caught, 'Could not load imported facts.')),
      )
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    const selected = fileInputRef.current?.files?.[0]
    if (!selected) return
    if (selected.size > MAX_BYTES) {
      setUploadError(`"${selected.name}" is larger than 2 MB. Choose a smaller file.`)
      return
    }
    setUploading(true)
    setUploadError(null)
    setUploadMessage(null)
    try {
      const created = await api.uploadProfileSource(selected)
      setSources((prev) => [summaryOf(created), ...(prev ?? [])])
      setOpenId(created.id)
      setDetail(created)
      setDetailError(null)
      setStaged({})
      setReviewMessage(null)
      setReviewError(null)
      setUploadMessage(
        `Uploaded. ${created.pending_count} imported fact${
          created.pending_count === 1 ? '' : 's'
        } waiting for review.`,
      )
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (caught) {
      setUploadError(failureMessage(caught, 'Upload failed.'))
    } finally {
      setUploading(false)
    }
  }

  async function handleReparse(id: string) {
    setBusyId(id)
    setActionError(null)
    try {
      const updated = await api.reparseProfileSource(id)
      setSources(
        (prev) => prev?.map((s) => (s.id === id ? summaryOf(updated) : s)) ?? prev,
      )
      if (openId === id) {
        setDetail(updated)
        setStaged({})
        setReviewMessage(null)
        setReviewError(null)
      }
    } catch (caught) {
      setActionError(failureMessage(caught, 'Could not re-parse the file.'))
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(source: ProfileSourceSummary) {
    const note =
      source.accepted_count > 0
        ? ' Accepted facts from it will be removed from matching, and opportunities will be rescored.'
        : ''
    const label = source.original_filename ?? 'this file'
    if (!window.confirm(`Delete ${label}?${note}`)) return
    setBusyId(source.id)
    setActionError(null)
    try {
      const result = await api.deleteProfileSource(source.id)
      setSources((prev) => prev?.filter((s) => s.id !== source.id) ?? prev)
      if (openId === source.id) {
        setOpenId(null)
        resetPanel()
      }
      setUploadMessage(
        rescoreMessage(
          result.catalog_pass,
          result.evaluated_opportunities,
          result.unchanged_opportunities,
        ),
      )
    } catch (caught) {
      setActionError(failureMessage(caught, 'Could not delete the file.'))
    } finally {
      setBusyId(null)
    }
  }

  function stageAccept(fact: ImportedFact) {
    setStaged((prev) => ({
      ...prev,
      [fact.id]: {
        action: 'accept',
        name: fact.name,
        description: fact.description ?? '',
      },
    }))
  }

  function stageReject(factId: string) {
    setStaged((prev) => ({
      ...prev,
      [factId]: { action: 'reject', name: '', description: '' },
    }))
  }

  function unstage(factId: string) {
    setStaged((prev) => {
      const next = { ...prev }
      delete next[factId]
      return next
    })
  }

  function updateStagedField(
    factId: string,
    field: 'name' | 'description',
    value: string,
  ) {
    setStaged((prev) => {
      const current = prev[factId]
      if (!current) return prev
      return { ...prev, [factId]: { ...current, [field]: value } }
    })
  }

  function stageAll(facts: ImportedFact[], action: 'accept' | 'reject') {
    setStaged((prev) => {
      const next = { ...prev }
      for (const fact of facts) {
        if (fact.review_state !== 'pending') continue
        next[fact.id] =
          action === 'accept'
            ? { action, name: fact.name, description: fact.description ?? '' }
            : { action, name: '', description: '' }
      }
      return next
    })
  }

  async function handleApply() {
    if (!detail) return
    const body = buildReviewBody(detail.facts, staged)
    setSaving(true)
    setReviewError(null)
    try {
      const result = await api.reviewProfileSource(detail.id, body)
      setDetail(result.source)
      setSources(
        (prev) =>
          prev?.map((s) => (s.id === result.source.id ? summaryOf(result.source) : s)) ??
          prev,
      )
      setStaged({})
      setReviewMessage(
        rescoreMessage(
          result.catalog_pass,
          result.evaluated_opportunities,
          result.unchanged_opportunities,
        ),
      )
    } catch (caught) {
      setReviewError(failureMessage(caught, 'Could not save review changes.'))
    } finally {
      setSaving(false)
    }
  }

  if (loadError)
    return (
      <div className="space-y-4">
        <ProfileTabs />
        <ErrorMessage>{loadError}</ErrorMessage>
      </div>
    )
  if (!sources)
    return (
      <div className="space-y-4">
        <ProfileTabs />
        <p role="status">Loading imported files…</p>
      </div>
    )

  const stagedCount = Object.keys(staged).length
  const pendingFactCount =
    detail?.facts.filter((f) => f.review_state === 'pending').length ?? 0

  return (
    <div className="space-y-6">
      <ProfileTabs />
      <h1 className="text-2xl font-semibold">Profile sources</h1>
      <p className="text-slate-600">
        Upload a resume to import facts automatically. Imported facts never affect
        matching until you accept them here. Only Skills, Courses, Projects, and Research
        affect fit today; education, awards, and other categories are kept for reference
        and never change eligibility. Edit eligibility on the Eligibility Profile tab.
      </p>

      <form onSubmit={handleUpload} className={fieldsetClass}>
        <label htmlFor="resume-file" className="block text-sm font-medium">
          Upload a resume
        </label>
        <input
          id="resume-file"
          ref={fileInputRef}
          type="file"
          accept=".txt,.pdf,text/plain,application/pdf"
          className="mt-1 block w-full text-sm"
        />
        <p className="mt-1 text-xs text-slate-500">
          Text and text-based PDF only. Scanned PDFs aren't supported. Files stay private
          in your database. Maximum size 2 MB.
        </p>
        {uploadError && <ErrorMessage>{uploadError}</ErrorMessage>}
        {uploadMessage && <SuccessMessage>{uploadMessage}</SuccessMessage>}
        <button type="submit" disabled={uploading} className={buttonClass}>
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </form>

      {actionError && <ErrorMessage>{actionError}</ErrorMessage>}

      {sources.length === 0 ? (
        <p className="text-slate-600">No files uploaded yet.</p>
      ) : (
        <ul aria-label="Imported files" className="space-y-3">
          {sources.map((source) => (
            <li key={source.id} className="rounded border border-slate-200 p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {source.original_filename ?? 'Untitled file'}
                  </p>
                  <p className="text-sm text-slate-600">
                    {source.content_type === 'application/pdf' ? 'PDF' : 'Text'} ·{' '}
                    {Math.round(source.byte_size / 1024)} KB · Uploaded{' '}
                    {new Date(source.ingested_at).toLocaleDateString()} · Parsed by{' '}
                    {source.parser_name} v{source.parser_version}
                  </p>
                  <p className="mt-1 flex flex-wrap gap-1">
                    <Badge tone="amber">Pending {source.pending_count}</Badge>
                    <Badge tone="green">Accepted {source.accepted_count}</Badge>
                    <Badge tone="red">Rejected {source.rejected_count}</Badge>
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => toggleOpen(source.id)}
                    className={secondaryButtonClass}
                  >
                    {openId === source.id ? 'Hide facts' : 'View facts'}
                  </button>
                  <a
                    href={`/api/profile/sources/${encodeURIComponent(source.id)}/file`}
                    download
                    className={secondaryButtonClass}
                  >
                    Download
                  </a>
                  <button
                    type="button"
                    onClick={() => handleReparse(source.id)}
                    disabled={busyId === source.id}
                    className={secondaryButtonClass}
                  >
                    Re-parse
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(source)}
                    disabled={busyId === source.id}
                    className={dangerButtonClass}
                  >
                    Delete
                  </button>
                </div>
              </div>

              {openId === source.id && (
                <div className="mt-3 space-y-4 border-t border-slate-200 pt-3">
                  {detailError && <ErrorMessage>{detailError}</ErrorMessage>}
                  {!detail && !detailError && (
                    <p role="status">Loading imported facts…</p>
                  )}
                  {detail && (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => stageAll(detail.facts, 'accept')}
                            disabled={pendingFactCount === 0 || saving}
                            className={secondaryButtonClass}
                          >
                            Accept all pending
                          </button>
                          <button
                            type="button"
                            onClick={() => stageAll(detail.facts, 'reject')}
                            disabled={pendingFactCount === 0 || saving}
                            className={secondaryButtonClass}
                          >
                            Reject all pending
                          </button>
                        </div>
                        <button
                          type="button"
                          onClick={handleApply}
                          disabled={stagedCount === 0 || saving}
                          className={buttonClass}
                        >
                          {saving
                            ? 'Saving…'
                            : `Apply ${stagedCount} change${stagedCount === 1 ? '' : 's'}`}
                        </button>
                      </div>

                      {factCategories
                        .map((category) => ({
                          category,
                          facts: detail.facts.filter((f) => f.category === category),
                        }))
                        .filter((group) => group.facts.length > 0)
                        .map((group) => {
                          const pendingInGroup = group.facts.filter(
                            (f) => f.review_state === 'pending',
                          )
                          return (
                            <fieldset key={group.category} className={fieldsetClass}>
                              <legend className="px-1 font-medium">
                                {categoryLabels[group.category]}
                              </legend>
                              {!(
                                group.category === 'skill' ||
                                group.category === 'course' ||
                                group.category === 'project' ||
                                group.category === 'research'
                              ) && (
                                <p className="text-sm text-slate-600">
                                  Shown for reference only; this category does not affect
                                  fit.
                                </p>
                              )}
                              <div className="flex gap-2">
                                <button
                                  type="button"
                                  onClick={() => stageAll(pendingInGroup, 'accept')}
                                  disabled={pendingInGroup.length === 0 || saving}
                                  className={secondaryButtonClass}
                                >
                                  Accept all pending in {categoryLabels[group.category]}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => stageAll(pendingInGroup, 'reject')}
                                  disabled={pendingInGroup.length === 0 || saving}
                                  className={secondaryButtonClass}
                                >
                                  Reject all pending in {categoryLabels[group.category]}
                                </button>
                              </div>
                              <ul className="space-y-2">
                                {group.facts.map((fact) => {
                                  const stage = staged[fact.id]
                                  return (
                                    <li
                                      key={fact.id}
                                      className="space-y-2 rounded border border-slate-100 p-3"
                                    >
                                      <div className="flex flex-wrap items-center gap-2">
                                        <span className="font-medium">{fact.name}</span>
                                        <Badge>Imported</Badge>
                                        <StatusBadge state={fact.review_state} />
                                      </div>
                                      {fact.description && (
                                        <p className="text-sm text-slate-600">
                                          {fact.description}
                                        </p>
                                      )}
                                      <div className="flex gap-2">
                                        <button
                                          type="button"
                                          disabled={saving}
                                          onClick={() =>
                                            stage?.action === 'accept'
                                              ? unstage(fact.id)
                                              : stageAccept(fact)
                                          }
                                          className={secondaryButtonClass}
                                        >
                                          {stage?.action === 'accept'
                                            ? 'Cancel accept'
                                            : 'Accept'}
                                        </button>
                                        <button
                                          type="button"
                                          disabled={saving}
                                          onClick={() =>
                                            stage?.action === 'reject'
                                              ? unstage(fact.id)
                                              : stageReject(fact.id)
                                          }
                                          className={secondaryButtonClass}
                                        >
                                          {stage?.action === 'reject'
                                            ? 'Cancel reject'
                                            : 'Reject'}
                                        </button>
                                      </div>
                                      {stage?.action === 'accept' && (
                                        <div className="space-y-2">
                                          <Field
                                            id={`fact-${fact.id}-name`}
                                            label={`Name (${fact.name})`}
                                          >
                                            <input
                                              id={`fact-${fact.id}-name`}
                                              value={stage.name}
                                              maxLength={
                                                fact.category === 'skill' ? 100 : 150
                                              }
                                              onChange={(event) =>
                                                updateStagedField(
                                                  fact.id,
                                                  'name',
                                                  event.target.value,
                                                )
                                              }
                                              className={inputClass}
                                            />
                                          </Field>
                                          {hasDescription(fact.category) && (
                                            <Field
                                              id={`fact-${fact.id}-description`}
                                              label={`Description for ${fact.name} (optional)`}
                                            >
                                              <textarea
                                                id={`fact-${fact.id}-description`}
                                                value={stage.description}
                                                maxLength={2000}
                                                rows={2}
                                                onChange={(event) =>
                                                  updateStagedField(
                                                    fact.id,
                                                    'description',
                                                    event.target.value,
                                                  )
                                                }
                                                className={inputClass}
                                              />
                                            </Field>
                                          )}
                                        </div>
                                      )}
                                    </li>
                                  )
                                })}
                              </ul>
                            </fieldset>
                          )
                        })}

                      {reviewError && <ErrorMessage>{reviewError}</ErrorMessage>}
                      {reviewMessage && <SuccessMessage>{reviewMessage}</SuccessMessage>}
                    </>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
