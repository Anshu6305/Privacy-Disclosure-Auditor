/**
 * Declares that a report was produced with controlled stubs.
 *
 * The backend sets `uses_fixture_models` when any model behind an audit is a
 * fixture rather than a trained model. Carrying that to the top of the screen
 * is the whole point: a demonstration report and a real one are otherwise
 * indistinguishable to a reader, and the difference is the difference between
 * a finding and a worked example.
 */

export default function FixtureNotice({ usesFixtureModels }) {
  if (!usesFixtureModels) return null;
  return (
    <div className="fixture-notice" role="note">
      <strong>Produced with fixture models.</strong> The classifier and aligner
      behind this audit are controlled stubs, not trained models. The verdicts
      below demonstrate the pipeline; they are not model predictions and must
      not be read as findings about this application.
    </div>
  );
}
