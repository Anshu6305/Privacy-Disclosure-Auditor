"""The trained F-12 checkpoint, exercised for real.

Skipped unless both torch and the checkpoint are present, because neither is
committed: the checkpoint is 265 MB and git-ignored by design. A skip here is
a skip, never a pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = ROOT / "ml/checkpoints/span-extractor-v1"

pytestmark = pytest.mark.ml


@pytest.fixture(scope="module")
def extractor():
    pytest.importorskip("torch", reason="F-12 inference needs torch")
    pytest.importorskip("transformers")
    if not CHECKPOINT.is_dir():
        pytest.skip(f"no F-12 checkpoint at {CHECKPOINT}")
    import sys

    if str(ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(ROOT / "backend"))
    from app.services.model_registry import load_span_extractor

    return load_span_extractor()


POLICY = (
    "We collect your precise location to show nearby results. "
    "We also collect your email address and phone number for account setup. "
    "We use cookies for advertising and analytics purposes."
)


def test_the_checkpoint_loads_through_the_registry(extractor):
    assert extractor.threshold == 0.50


def test_it_predicts_both_span_types(extractor):
    spans = extractor.extract(POLICY, POLICY, 0)
    types = {span.span_type for span in spans}
    assert "data_type" in types, "no data-type span; F-15 would have nothing to key on"
    assert "purpose" in types


def test_every_predicted_span_is_an_exact_slice_of_the_document(extractor):
    """The property the whole evidence design rests on.

    A span whose offsets have drifted would quote text the policy does not
    contain. `SpanExtractor.extract` already raises on this; asserting it
    here as well means a regression names itself.
    """
    spans = extractor.extract(POLICY, POLICY, 0)
    assert spans
    for span in spans:
        assert POLICY[span.start : span.end] == span.text
        assert span.verify_against(POLICY)


def test_offsets_are_shifted_into_document_coordinates(extractor):
    """A segment is tagged in its own coordinates and reported in the
    document's. Getting this wrong points every quote at the wrong words."""
    prefix = "Introductory sentence that is not part of the segment. "
    document = prefix + POLICY
    spans = extractor.extract(POLICY, document, len(prefix))
    assert spans
    for span in spans:
        assert span.start >= len(prefix)
        assert document[span.start : span.end] == span.text


def test_a_predicted_value_is_one_the_model_was_trained_on(extractor):
    """A value outside the label set could never match an F-15 rule."""
    import json

    labels = json.loads((CHECKPOINT / "labels.json").read_text(encoding="utf-8"))
    known = {label.partition(":")[2] for label in labels if ":" in label}
    for span in extractor.extract(POLICY, POLICY, 0):
        assert span.value in known, span.value


def test_low_confidence_spans_are_flagged_not_dropped(extractor):
    """The model's exact-match F1 is 0.107, so most spans are uncertain.

    They must survive as abstained rather than disappear: a dropped span is
    indistinguishable from the policy not saying it, and that is how an
    uncertain prediction would become a confident absence finding.
    """
    spans = extractor.extract(POLICY, POLICY, 0)
    assert spans, "spans were dropped entirely"
    assert any(span.abstained for span in spans), (
        "nothing abstained on a model this uncertain; check the gate"
    )
    for span in spans:
        assert span.text, "an abstained span must still carry its text"


def test_the_registry_refuses_a_missing_checkpoint_rather_than_substituting(tmp_path):
    """No heuristic fallback. A different tagger moves span boundaries, so
    the same policy would produce different evidence on different machines."""
    import sys

    if str(ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(ROOT / "backend"))
    from app.services.model_registry import ModelsUnavailableError, load_span_extractor

    with pytest.raises(ModelsUnavailableError, match="no F-12 checkpoint"):
        load_span_extractor(tmp_path / "absent")
