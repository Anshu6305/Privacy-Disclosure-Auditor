"""F-13 — model variant binding.

FR-13 requires that an audit can run on either the baseline or the improved
model, so the two can be compared on the same input. F-13 is how that choice
is made, and the rules it must obey are all about not changing its mind:

* **one variant for the whole audit** — classifier, extractor and aligner
  are bound together, never mixed;
* **resolved through F-34**, the model registry, not from a path or a
  setting;
* **recorded on `audit_run`** as three `model_version_id` values, which is
  where the variant lives: there is no `variant` column, and none is needed,
  because every `model_version` row already carries one;
* **bound when the job is claimed, and never switched** during the audit;
* **an unknown variant is rejected before any work begins.**

**There is no fallback anywhere in this module.** If the improved variant is
asked for and is not registered for all three tasks, the request is refused.
Quietly running the baseline instead would produce a report whose provenance
says improved, which is the one outcome a comparison must never produce.

Per DD-8 the variant is internal: end-user requests omit it and get the
active set, and the Corpus Maintainer passes it through command-line tooling
when running a comparison. Nothing in the frontend selects a variant.
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.vocabulary import MODEL_TASKS, MODEL_VARIANTS


class UnknownVariantError(ValueError):
    """A variant outside the approved vocabulary. Rejected before work."""


class VariantUnavailableError(RuntimeError):
    """The variant is valid but not registered for every task."""


class MixedVariantError(RuntimeError):
    """The active registrations do not agree on a single variant.

    F-13 binds one variant for the whole audit. If the active classifier is
    improved while the active aligner is baseline, there is no single
    variant to bind and no honest label for the result, so the audit is
    refused rather than run on a mixture nobody chose.
    """


@dataclass(frozen=True, slots=True)
class VariantBinding:
    """One resolved version set: the variant, and a model id per task."""

    variant: str
    model_version_ids: dict[str, int]

    def __post_init__(self) -> None:
        missing = set(MODEL_TASKS) - set(self.model_version_ids)
        if missing:
            raise VariantUnavailableError(
                f"the binding is missing a model for {sorted(missing)}"
            )


def normalise_variant(value: str | None) -> str | None:
    """Validate a requested variant. ``None`` means "use the active set".

    Raises before any work begins, which is where F-13 requires an unknown
    variant to be caught: refusing after the policy has been fetched and
    segmented would waste the work and leave a half-finished audit behind.
    """
    if value is None:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if candidate not in MODEL_VARIANTS:
        raise UnknownVariantError(
            f"unknown model variant {value!r}; the approved variants are "
            f"{', '.join(MODEL_VARIANTS)}"
        )
    return candidate


def bind_variant(active_by_task: dict[str, object], variant: str | None) -> str:
    """The single variant this audit runs under.

    With a variant requested, that is the answer and every task must provide
    it. Without one, the active registrations decide — and they must agree,
    or there is nothing to bind.
    """
    if variant is not None:
        return variant

    variants = {getattr(model, "variant", None) for model in active_by_task.values()}
    if len(variants) != 1:
        raise MixedVariantError(
            "the active model versions span more than one variant "
            f"({sorted(str(v) for v in variants)}). F-13 binds one variant "
            "for the whole audit, so there is nothing to bind. Activate one "
            "variant for every task."
        )
    return next(iter(variants))


__all__ = [
    "MixedVariantError",
    "UnknownVariantError",
    "VariantBinding",
    "VariantUnavailableError",
    "bind_variant",
    "normalise_variant",
]
