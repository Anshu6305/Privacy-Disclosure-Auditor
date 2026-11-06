/**
 * One of ALG-8's five verdicts, plus the abstention flag.
 *
 * Colour never carries the meaning alone: the verdict is always written out,
 * and `abstention_involved` is shown as its own marker rather than folded
 * into the verdict, because an Undetermined reached through abstention and a
 * confident Consistent are not points on one scale.
 */

const SLUG = {
  Consistent: 'consistent',
  'Declared-not-in-policy': 'declared-only',
  'In-policy-not-declared': 'policy-only',
  Contradictory: 'contradictory',
  Undetermined: 'undetermined',
};

export default function VerdictBadge({ verdict, abstentionInvolved }) {
  return (
    <span className="verdict-cell">
      <span className="verdict" data-verdict={SLUG[verdict] ?? 'unknown'}>
        {verdict}
      </span>
      {abstentionInvolved ? (
        <span
          className="verdict__abstained"
          title="At least one model abstained; this verdict rests on incomplete evidence."
        >
          abstention involved
        </span>
      ) : null}
    </span>
  );
}
