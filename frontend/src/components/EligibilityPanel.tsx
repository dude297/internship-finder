import { Link } from 'react-router'
import type { OpportunityDetail } from '../api/schemas'
import { ruleSummary, ruleTitle } from '../lib/eligibility'
import { eligibilityLabels, formatDateTime } from '../lib/labels'
import { EligibilityBadge } from './EligibilityBadge'

export function EligibilityPanel({ opportunity }: { opportunity: OpportunityDetail }) {
  const evaluation = opportunity.latest_evaluation
  if (!evaluation) {
    return (
      <section aria-labelledby="eligibility-heading" className="rounded border p-4">
        <h2 id="eligibility-heading" className="text-lg font-semibold">
          Eligibility
        </h2>
        <p className="mt-2">
          <EligibilityBadge status={null} />{' '}
          {opportunity.profile_exists ? (
            'This opportunity has not been evaluated yet.'
          ) : (
            <>
              Eligibility can't be evaluated until you{' '}
              <Link to="/profile" className="text-blue-800 underline">
                fill in your profile
              </Link>
              .
            </>
          )}
        </p>
      </section>
    )
  }

  const requirements = new Map(opportunity.requirements.map((r) => [r.id, r]))
  const projected = evaluation.rule_results.filter((r) => r.depends_on_projected_status)
  return (
    <section
      aria-labelledby="eligibility-heading"
      className="space-y-3 rounded border p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="eligibility-heading" className="text-lg font-semibold">
          Eligibility
        </h2>
        <EligibilityBadge status={evaluation.eligibility_status} />
        <span className="text-sm text-slate-600">
          Evaluated {formatDateTime(evaluation.evaluated_at)}
        </span>
      </div>

      {evaluation.depends_on_projected_status && (
        <div
          role="note"
          className="rounded border border-sky-200 bg-sky-50 p-3 text-sky-900"
        >
          <p>This result depends on expected future education dates.</p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {projected.map((r, i) => (
              <li key={i}>
                {typeof r.details?.explanation === 'string'
                  ? r.details.explanation
                  : r.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ul className="space-y-2">
        {evaluation.rule_results.map((result, i) => {
          const requirement = result.requirement_id
            ? requirements.get(result.requirement_id)
            : undefined
          return (
            <li key={i} className="rounded border border-slate-100 p-3">
              <p>
                <span className="font-medium">{ruleTitle(result, requirement)}</span>
                {' — '}
                <span>{eligibilityLabels[result.status]}</span>
              </p>
              <p className="text-sm text-slate-700">{ruleSummary(result)}</p>
              <details className="mt-1 text-xs text-slate-500">
                <summary>More detail</summary>
                <p>{result.reason}</p>
                <p>
                  Rule {result.rule_id} · rules {evaluation.eligibility_rules_version}
                </p>
              </details>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
