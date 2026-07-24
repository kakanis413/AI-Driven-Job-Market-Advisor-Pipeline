/** A tiny inline chip for a metric with no value yet — so a missing number reads
 *  as an intentional, honest state ("Not scored yet") rather than a broken lone
 *  em dash. Tokens only; never fabricates a value. Pair `clock` with temporal
 *  gaps ("not scored yet") and leave it off for plain "No data". */
export default function DataChip({ label, clock }: { label: string; clock?: boolean }) {
  return (
    <span className="micro inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-line bg-raised px-2 py-0.5 text-ink3">
      {clock && (
        <svg width="9" height="9" viewBox="0 0 12 12" fill="none" aria-hidden className="shrink-0">
          <circle cx="6" cy="6" r="4.6" stroke="currentColor" strokeWidth="1.2" />
          <path d="M6 3.4V6l1.8 1.1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {label}
    </span>
  )
}
