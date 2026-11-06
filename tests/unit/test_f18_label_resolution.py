"""F-18's NLI head mapping.

The failure this guards is silent and total: if entailment and contradiction
indices are swapped, every SUPPORTS becomes a CONTRADICTS and the system
reports the opposite of what each policy says, while every test that does not
check the mapping still passes.

Published NLI heads genuinely disagree about order, so the mapping is read
from the model's own `id2label` and never assumed. These tests use real
`id2label` dictionaries, so they need no checkpoint and no torch.
"""

from __future__ import annotations

import pytest

from ml.backends import resolve_nli_label_indices

# The head orders three published NLI models actually use.
ROBERTA_LARGE_MNLI = {0: "CONTRADICTION", 1: "NEUTRAL", 2: "ENTAILMENT"}
CROSS_ENCODER = {0: "contradiction", 1: "entailment", 2: "neutral"}
BART_LARGE_MNLI = {0: "contradiction", 1: "neutral", 2: "entailment"}


@pytest.mark.parametrize(
    ("id2label", "expected"),
    [
        (ROBERTA_LARGE_MNLI, {"contradiction": 0, "neutral": 1, "entailment": 2}),
        (CROSS_ENCODER, {"contradiction": 0, "entailment": 1, "neutral": 2}),
        (BART_LARGE_MNLI, {"contradiction": 0, "neutral": 1, "entailment": 2}),
    ],
)
def test_the_index_comes_from_the_model_not_from_a_convention(id2label, expected):
    assert resolve_nli_label_indices(id2label) == expected


def test_entailment_and_contradiction_are_never_confused():
    """Stated as its own test because it is the whole point.

    Two of the three heads above put entailment at a different index. A fixed
    order would invert the verdicts for one of them.
    """
    cross = resolve_nli_label_indices(CROSS_ENCODER)
    roberta = resolve_nli_label_indices(ROBERTA_LARGE_MNLI)
    assert cross["entailment"] != roberta["entailment"]
    assert cross["entailment"] == 1
    assert roberta["entailment"] == 2


def test_case_and_whitespace_do_not_matter():
    assert resolve_nli_label_indices(
        {0: " Entailment ", 1: "NEUTRAL", 2: "contradiction"}
    ) == {"entailment": 0, "neutral": 1, "contradiction": 2}


def test_an_unlabelled_head_is_refused_rather_than_guessed():
    """`LABEL_0/1/2` carries no information about which class is which.

    Guessing would produce a model that looks like it works.
    """
    with pytest.raises(ValueError, match="does not expose the NLI labels"):
        resolve_nli_label_indices({0: "LABEL_0", 1: "LABEL_1", 2: "LABEL_2"})


def test_a_two_class_head_is_refused():
    with pytest.raises(ValueError, match="neutral"):
        resolve_nli_label_indices({0: "entailment", 1: "contradiction"})


def test_two_labels_resolving_to_one_index_are_refused():
    """A real shape, not a contrived one.

    `config.json` stores `id2label` with string keys; transformers converts
    them to ints, a raw `json.load` does not. A config read both ways can
    present "0" and 0 as separate entries that collapse onto index 0. The
    head is then uninterpretable, and two NLI classes would silently share a
    probability.
    """
    with pytest.raises(ValueError, match="share an output index"):
        resolve_nli_label_indices(
            {0: "entailment", "0": "neutral", 1: "contradiction"}
        )
