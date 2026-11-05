"""F-08 — reduce a raw policy document to policy prose (ALG-1, first stage).

What is removed is deliberately narrow: scripts, styles, and the structural
chrome of a web page. Nothing is removed because it looks repetitive, boilerplate
or unimportant. Privacy policies are repetitive by nature — "we may collect"
recurs a dozen times, definitions restate each other, and the same exception is
qualified in three sections — and a cleaner that judged content by how often it
had seen something similar would delete exactly the clauses the audit exists to
find.

Headings, definitions, legal qualifications, exceptions and list items are all
kept, because each can carry a data practice.

Determinism matters as much as accuracy here. F-09's offsets index this
module's output, so the same raw document must always produce the same cleaned
text. Nothing in this module depends on dictionary ordering, randomness or
wall-clock time.

Complexity: O(n) in the document length.
"""

from __future__ import annotations

import re
import unicodedata

from acquisition.models import PolicyDocument
from analysis.text.models import ExtractionResult

#: Removed entirely, with their contents. None of these carries policy prose.
_DISCARDED_TAGS: tuple[str, ...] = (
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
    "object",
    "embed",
    "form",
    "button",
    "input",
    "select",
    "textarea",
    "nav",
    "header",
    "footer",
    "aside",
)

#: Tags that end a block of text. A paragraph break is inserted after each so
#: F-09 can group by paragraph and a heading never runs into the prose beneath
#: it.
_BLOCK_TAGS: tuple[str, ...] = (
    "p", "div", "section", "article", "main",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "dt", "dd", "tr", "td", "th",
    "blockquote", "pre", "figcaption", "caption", "br", "hr",
)

#: Three or more newlines collapse to a paragraph break; a paragraph break is
#: exactly two, so F-09's paragraph splitting has one thing to look for.
_MANY_NEWLINES = re.compile(r"\n{3,}")
#: Runs of spaces and tabs, but never newlines, which carry structure.
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
#: Trailing and leading spaces on a line.
_LINE_EDGES = re.compile(r"[^\S\n]*\n[^\S\n]*")
#: A lone newline, not part of a blank line. In HTML a newline in the source
#: is ordinary whitespace and renders as a space, so one that survives into a
#: quoted sentence would be a line break the policy never had. Block
#: boundaries are written as two newlines and are left alone.
_SINGLE_NEWLINE = re.compile(r"(?<!\n)\n(?!\n)")

#: Characters that look like text but are not, and would otherwise survive
#: into a quoted sentence as invisible noise.
_ZERO_WIDTH = dict.fromkeys(
    map(ord, "​‌‍⁠﻿­"), None
)


class ExtractionError(Exception):
    """Raised only for a programming error, never for a bad document.

    A bad document produces a failed :class:`ExtractionResult`, because a
    corpus of 300 applications must not stop because one policy is malformed.
    """


def normalise_unicode(text: str) -> str:
    """NFKC, with invisible characters dropped.

    NFKC folds compatibility forms — ligatures, full-width Latin, the various
    non-breaking spaces — so that a sentence quoted from the policy reads as
    its author wrote it and matches when compared. It is applied before
    offsets are assigned, so the cleaned text and the offsets agree.
    """
    text = text.translate(_ZERO_WIDTH)
    text = unicodedata.normalize("NFKC", text)
    # NFKC maps U+00A0 to a plain space already; this catches the rest.
    return text.replace(" ", "\n").replace(" ", "\n\n")


def normalise_whitespace(text: str) -> str:
    """Collapse runs of space, trim line edges, cap blank runs at one.

    Line structure is preserved because F-09 groups by paragraph. What goes is
    only the indentation and ragged spacing that HTML leaves behind.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = _LINE_EDGES.sub("\n", text)
    text = _MANY_NEWLINES.sub("\n\n", text)
    # A single newline came from source whitespace, not from structure.
    text = _SINGLE_NEWLINE.sub(" ", text)
    # Collapsing may have produced new runs of spaces at the join.
    text = _HORIZONTAL_SPACE.sub(" ", text)
    return text.strip()


def _extract_from_html(markup: str, removed: dict[str, int]) -> str:
    """Strip markup with BeautifulSoup, keeping block structure."""
    from bs4 import BeautifulSoup

    soup = None
    for parser in ("lxml", "html5lib", "html.parser"):
        try:
            soup = BeautifulSoup(markup, parser)
            break
        except Exception:  # noqa: BLE001 - try the next parser
            continue
    if soup is None:  # pragma: no cover - html.parser accepts anything
        raise ExtractionError("no HTML parser could read the document")

    for tag_name in _DISCARDED_TAGS:
        for element in soup.find_all(tag_name):
            removed[tag_name] = removed.get(tag_name, 0) + 1
            element.decompose()

    # Comments carry no policy text and often hold template markup.
    from bs4 import Comment

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        removed["comment"] = removed.get("comment", 0) + 1
        comment.extract()

    # A paragraph break after every block element, so a heading and the prose
    # under it do not merge into one sentence.
    for tag_name in _BLOCK_TAGS:
        for element in soup.find_all(tag_name):
            element.append("\n\n")

    return soup.get_text()


def extract_policy_text(
    source: PolicyDocument | str,
    media_type: str | None = None,
    source_sha256: str | None = None,
) -> ExtractionResult:
    """Reduce a raw document to policy prose.

    Accepts either a :class:`~acquisition.models.PolicyDocument` from F-05 or
    a raw string. The original is never modified: the document is read, not
    written, and a string argument is not mutated.

    Returns a failed result rather than raising for every condition a real
    corpus produces — an empty document, markup with no text, an unsupported
    format. Only a programming error raises.
    """
    if isinstance(source, PolicyDocument):
        markup = source.content
        media_type = media_type or source.media_type
        source_sha256 = source_sha256 or source.content_sha256
    else:
        markup = source
        media_type = media_type or "text/html"

    if not isinstance(markup, str):
        raise ExtractionError(
            f"expected text, got {type(markup).__name__}; F-05 decodes the "
            "document before this point"
        )

    if media_type == "application/pdf":
        return ExtractionResult(
            text="",
            succeeded=False,
            source_sha256=source_sha256,
            media_type=media_type,
            reason=(
                "PDF text extraction is not implemented. The document is "
                "stored and can be re-processed once it is."
            ),
        )

    if not markup.strip():
        return ExtractionResult(
            text="",
            succeeded=False,
            source_sha256=source_sha256,
            media_type=media_type,
            reason="The document is empty.",
        )

    removed: dict[str, int] = {}

    if media_type == "text/plain":
        text = markup
    else:
        try:
            text = _extract_from_html(markup, removed)
        except ExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad document, not a crash
            return ExtractionResult(
                text="",
                succeeded=False,
                source_sha256=source_sha256,
                media_type=media_type,
                reason=f"HTML could not be parsed: {type(exc).__name__}: {exc}",
                removed=removed,
            )

    text = normalise_whitespace(normalise_unicode(text))

    if not text:
        return ExtractionResult(
            text="",
            succeeded=False,
            source_sha256=source_sha256,
            media_type=media_type,
            reason=(
                "The document contains markup but no readable text. It may be "
                "a page whose content loads from a script, which this project "
                "does not execute."
            ),
            removed=removed,
        )

    return ExtractionResult(
        text=text,
        succeeded=True,
        source_sha256=source_sha256,
        media_type=media_type,
        reason=None,
        removed=removed,
    )
