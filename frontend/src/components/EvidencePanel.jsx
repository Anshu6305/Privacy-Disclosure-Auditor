/**
 * F-25 — the evidence behind one category's verdict.
 *
 * Three record types, rendered as three different things, because they are
 * three different claims:
 *
 *   evidence      verbatim policy text with its character offsets. Shown as a
 *                 quotation and never edited, truncated mid-sentence or
 *                 paraphrased.
 *   absence       a system-generated statement that the policy says nothing.
 *                 It carries no quote, and rendering it as one would attribute
 *                 words to the policy that the policy does not contain.
 *   inconclusive  the system was not confident enough to decide.
 *
 * A category with no records is not an error: a Consistent verdict carries no
 * evidence record by design (F-23), and the panel says so rather than looking
 * broken.
 */

import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { Failed, Loading } from './Async.jsx';

const INTRO = {
  evidence: 'Quoted from the privacy policy',
  absence: 'Nothing found in the privacy policy',
  inconclusive: 'Not decided',
};

export default function EvidencePanel({ auditId, dsCategory, verdict }) {
  const [records, setRecords] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .categoryEvidence(auditId, dsCategory)
      .then((data) => !cancelled && setRecords(data))
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [auditId, dsCategory]);

  if (error) return <Failed error={error} what={`evidence for ${dsCategory}`} />;
  if (!records) return <Loading what="evidence" />;

  if (records.length === 0) {
    return (
      <p className="evidence__none">
        {verdict === 'Consistent'
          ? 'No evidence record: both sources agree, and an agreement is not quoted (F-23).'
          : 'No evidence records were stored for this category.'}
      </p>
    );
  }

  return (
    <ul className="evidence">
      {records.map((record, index) => (
        <li
          key={`${record.record_type}-${record.display_order}-${index}`}
          className={`evidence__item evidence__item--${record.record_type}`}
        >
          <p className="evidence__label">{INTRO[record.record_type] ?? record.record_type}</p>

          {record.record_type === 'evidence' && record.quoted_text ? (
            <>
              <blockquote className="evidence__quote">{record.quoted_text}</blockquote>
              <p className="evidence__offsets">
                Characters {record.char_start}–{record.char_end} of the cleaned
                policy text
                {record.segment_id != null ? `, segment ${record.segment_id}` : ''}
              </p>
            </>
          ) : null}

          {record.reason ? <p className="evidence__reason">{record.reason}</p> : null}
        </li>
      ))}
    </ul>
  );
}
