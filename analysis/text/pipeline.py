"""T2 end to end: F-05 → F-08 → F-09 → F-10.

A thin orchestration over the three functions, plus the M3A loader. It exists
so the sequence is written down once and tested as a whole, and so the cleaned
text can be stored next to the raw document.

**Why the cleaned text is stored.** F-09's offsets index it. Without it a
reader following an offset from an audit report has nothing to count
characters in, and F-25's highlighting has no document to highlight. It is
written to the corpus ``processed/`` directory, which M3A keeps separate from
``raw/`` so a derived file can never overwrite a source document.

Nothing here touches a database. Persistence of segments is M3B and M8.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acquisition.models import PolicyDocument
from analysis.text.extractor import extract_policy_text
from analysis.text.models import (
    AnalysabilityResult,
    AnalysabilityThresholds,
    ExtractionResult,
    PolicySegment,
)
from analysis.text.segmenter import DEFAULT_MAX_SEGMENT_CHARS, segment_policy_text
from analysis.text.validator import validate_analysability


@dataclass(frozen=True)
class ProcessedPolicy:
    """Everything T2 produces for one policy document."""

    package_name: str
    extraction: ExtractionResult
    segments: tuple[PolicySegment, ...]
    analysability: AnalysabilityResult

    @property
    def cleaned_text(self) -> str:
        """The canonical document the segment offsets index."""
        return self.extraction.text

    @property
    def ready_for_analysis(self) -> bool:
        return self.extraction.succeeded and self.analysability.analysable


def process_policy_document(
    document: PolicyDocument,
    thresholds: AnalysabilityThresholds | None = None,
    allow_provisional: bool = False,
    max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS,
    nlp: Any | None = None,
) -> ProcessedPolicy:
    """Run F-08, F-09 and F-10 over a document loaded by F-05.

    A failed extraction still returns a result: segmentation yields nothing
    and F-10 records why the audit cannot proceed. The pipeline does not raise
    for a bad document, because one unreadable policy in a corpus of hundreds
    must not stop the rest.
    """
    extraction = extract_policy_text(document)

    segments: tuple[PolicySegment, ...] = ()
    if extraction.succeeded:
        segments = tuple(
            segment_policy_text(
                extraction.text, max_segment_chars=max_segment_chars, nlp=nlp
            )
        )

    analysability = validate_analysability(
        segments, thresholds=thresholds, allow_provisional=allow_provisional
    )

    if not extraction.succeeded:
        # F-10's generic "no segments" message is true but unhelpful here; the
        # extraction knows precisely what went wrong and the audit record
        # should carry that instead.
        analysability = AnalysabilityResult(
            analysable=False,
            reason=f"Text extraction failed: {extraction.reason}",
            segment_count=0,
            token_count=0,
            thresholds=analysability.thresholds,
        )

    return ProcessedPolicy(
        package_name=document.package_name,
        extraction=extraction,
        segments=segments,
        analysability=analysability,
    )


def write_cleaned_text(processed: ProcessedPolicy, processed_dir: Path | str) -> Path:
    """Store the cleaned text the offsets index, named by the source hash.

    Named after the **source** document's hash, so the link between a raw
    document and the cleaned text derived from it is explicit.
    """
    if not processed.extraction.succeeded:
        raise ValueError("there is no cleaned text to write: extraction failed")

    digest = processed.extraction.source_sha256
    if not digest:
        raise ValueError(
            "the extraction has no source hash, so the cleaned text cannot be "
            "tied to the document it came from"
        )

    directory = Path(processed_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.txt"
    path.write_text(processed.cleaned_text, encoding="utf-8")
    return path
