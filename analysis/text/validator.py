"""F-10 — decide whether a policy document is worth analysing.

This is the error path. Phase 3 is explicit that an unanalysable document
terminates the audit with a recorded reason, rather than producing empty
verdicts. The distinction matters to a reader: fourteen Consistent verdicts
because neither source mentioned anything looks identical to fourteen
Consistent verdicts because the policy was a 404 page, and only one of those
is a finding.

Thresholds are **never defaulted silently**. The caller passes them, or
explicitly asks for the documented provisional values. A missing or invalid
configuration raises rather than guessing, because a threshold quietly set to
zero would accept an empty document.

Complexity: O(S) over the segments.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from analysis.text.models import (
    PROVISIONAL_THRESHOLDS,
    AnalysabilityResult,
    AnalysabilityThresholds,
    PolicySegment,
)


class ThresholdConfigurationError(ValueError):
    """The analysability thresholds are missing or unusable.

    Raised rather than falling back to a default. Phase 3 requires the
    comparison against "a configured minimum"; a value the operator did not
    choose is not a configured minimum, and an audit run would record a
    threshold nobody set.
    """


def thresholds_from_config(
    config: Mapping[str, Any] | None,
    allow_provisional: bool = False,
) -> AnalysabilityThresholds:
    """Build thresholds from a configuration mapping.

    ``allow_provisional`` must be set explicitly for the documented
    provisional values to be used. It is not the default, so a caller cannot
    end up on them by omission.
    """
    if config is None:
        if allow_provisional:
            return PROVISIONAL_THRESHOLDS
        raise ThresholdConfigurationError(
            "No analysability thresholds were configured. Pass them, or pass "
            "allow_provisional=True to accept the documented provisional "
            "values (min_segments="
            f"{PROVISIONAL_THRESHOLDS.min_segments}, min_tokens="
            f"{PROVISIONAL_THRESHOLDS.min_tokens}), which are the project's "
            "own proposal and not an approved requirement."
        )

    if not isinstance(config, Mapping):
        raise ThresholdConfigurationError(
            f"threshold configuration must be a mapping, got {type(config).__name__}"
        )

    missing = [k for k in ("min_segments", "min_tokens") if k not in config]
    if missing:
        raise ThresholdConfigurationError(
            f"threshold configuration is missing {missing}. Both are required; "
            f"an absent threshold is not the same as a threshold of zero."
        )

    values = {}
    for key in ("min_segments", "min_tokens"):
        raw = config[key]
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ThresholdConfigurationError(
                f"{key} must be an integer, got {type(raw).__name__} ({raw!r})"
            )
        values[key] = raw

    try:
        return AnalysabilityThresholds(**values)
    except ValueError as exc:
        raise ThresholdConfigurationError(str(exc)) from exc


def validate_analysability(
    segments: Sequence[PolicySegment],
    thresholds: AnalysabilityThresholds | None = None,
    allow_provisional: bool = False,
) -> AnalysabilityResult:
    """Decide whether these segments can be analysed, and say why.

    A successful result carries a reason too, so the audit record states why
    the document was accepted and not only that it was.
    """
    if thresholds is None:
        if not allow_provisional:
            raise ThresholdConfigurationError(
                "No thresholds supplied. Pass an AnalysabilityThresholds, or "
                "pass allow_provisional=True to accept the documented "
                "provisional values."
            )
        thresholds = PROVISIONAL_THRESHOLDS

    segment_count = len(segments)
    token_count = sum(segment.token_count for segment in segments)

    if segment_count == 0:
        return AnalysabilityResult(
            analysable=False,
            reason=(
                "The policy document produced no segments. Either extraction "
                "failed or the document contains no readable text. No "
                "classification or verdict assignment is possible."
            ),
            segment_count=0,
            token_count=0,
            thresholds=thresholds,
        )

    if token_count == 0:
        return AnalysabilityResult(
            analysable=False,
            reason=(
                f"The document produced {segment_count} segment(s) but no "
                f"tokens. There is no text to analyse."
            ),
            segment_count=segment_count,
            token_count=0,
            thresholds=thresholds,
        )

    failures = []
    if segment_count < thresholds.min_segments:
        failures.append(
            f"{segment_count} segment(s), below the minimum of "
            f"{thresholds.min_segments}"
        )
    if token_count < thresholds.min_tokens:
        failures.append(
            f"{token_count} token(s), below the minimum of {thresholds.min_tokens}"
        )

    if failures:
        return AnalysabilityResult(
            analysable=False,
            reason=(
                "The document has too little usable text to analyse: "
                + "; ".join(failures)
                + ". This is commonly an error page, a consent banner or a "
                "page whose content loads from a script. The audit stops here "
                "rather than reporting verdicts drawn from nothing."
            ),
            segment_count=segment_count,
            token_count=token_count,
            thresholds=thresholds,
        )

    return AnalysabilityResult(
        analysable=True,
        reason=(
            f"The document has {segment_count} segment(s) and {token_count} "
            f"token(s), meeting the minimums of {thresholds.min_segments} and "
            f"{thresholds.min_tokens}."
        ),
        segment_count=segment_count,
        token_count=token_count,
        thresholds=thresholds,
    )
