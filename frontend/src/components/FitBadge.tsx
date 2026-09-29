/** The backend's fit score, with a note when the profile covered only part of it. Fit never
 * decides eligibility; the eligibility badge sits next to it. */
export function FitBadge({
  score,
  coverage,
}: {
  score: number | null
  coverage: number | null
}) {
  if (score === null)
    return <span className="text-sm text-slate-500">Fit not scored yet</span>
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="inline-block rounded bg-indigo-100 px-2 py-0.5 text-sm font-medium text-indigo-900">
        Fit {score}
      </span>
      {coverage !== null && coverage < 100 && (
        <span className="text-xs text-slate-500">({coverage}% of fit measured)</span>
      )}
    </span>
  )
}
