import type { OpportunityDetail } from '../api/schemas'
import {
  availabilityLabels,
  formatDateTime,
  formatDay,
  sourceHealthLabels,
} from '../lib/labels'

/** Where the opportunity was seen. Only safe fields; raw source payloads never reach the UI. */
export function SourceProvenance({ opportunity }: { opportunity: OpportunityDetail }) {
  return (
    <section aria-labelledby="source-heading" className="space-y-2">
      <h2 id="source-heading" className="text-lg font-semibold">
        Source
      </h2>
      <p>
        <span className="text-slate-500">Status: </span>
        {availabilityLabels[opportunity.availability]}
        {opportunity.origin === 'imported' && opportunity.manually_curated_at && (
          <span className="text-slate-600">
            {' '}
            · Your edits from {formatDateTime(opportunity.manually_curated_at)} are kept
            when sources sync
          </span>
        )}
      </p>
      <ul className="space-y-2">
        {opportunity.sources.map((record, index) => (
          <li key={index} className="rounded border border-slate-200 p-3 text-sm">
            <p className="font-medium">
              {record.source_name}{' '}
              {record.automated && (
                <span
                  className={`ml-1 rounded px-1.5 py-0.5 text-xs ${
                    record.is_active ? 'bg-green-100 text-green-800' : 'bg-slate-200'
                  }`}
                >
                  {record.is_active ? 'Active' : 'Closed'}
                </span>
              )}
            </p>
            <p className="text-slate-600">
              First seen {formatDay(record.first_seen_at)} · Last seen{' '}
              {formatDay(record.last_seen_at)}
              {record.closed_at && ` · Closed ${formatDay(record.closed_at)}`}
            </p>
            {record.automated && (
              <p className="text-slate-600">
                Sync health:{' '}
                {record.source_health
                  ? sourceHealthLabels[record.source_health]
                  : 'Unknown'}
                {' · Last successful sync: '}
                {record.source_last_success_at
                  ? formatDateTime(record.source_last_success_at)
                  : 'never'}
              </p>
            )}
            {record.source_url && (
              <a
                href={record.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-800 underline"
              >
                Original posting
              </a>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
