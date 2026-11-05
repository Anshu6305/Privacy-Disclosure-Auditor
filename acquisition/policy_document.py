"""F-05 — load a stored privacy policy document and verify its hash.

The raw document is never modified. This module opens it read-only, hashes
the bytes it read, compares that against the hash recorded in the corpus, and
returns the text. Extraction and segmentation are F-08 and F-09 in Milestone 4
and consume :class:`PolicyDocument` from here.

Why the hash is checked on every load rather than only at import: the corpus
is a frozen artefact that six people share and copy between machines, and a
truncated or re-saved file is the kind of corruption that produces a plausible
but wrong audit. A mismatch stops the load with both hashes reported.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from acquisition.models import PolicyDocument, Provenance

#: Read in blocks so a large document does not have to be held twice.
_BLOCK = 1 << 20

#: Extensions the corpus stores. A policy is HTML, text, or occasionally PDF.
MEDIA_TYPES: dict[str, str] = {
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".pdf": "application/pdf",
}


class PolicyDocumentError(Exception):
    """Base class for policy loading failures."""


class PolicyFileMissingError(PolicyDocumentError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"Policy document not found: {path}\n"
            f"  The corpus record references a file that is not present. "
            f"Either the corpus was copied without its raw documents, or the "
            f"record was written before the document was stored."
        )
        self.path = path


class PolicyHashMismatchError(PolicyDocumentError):
    """The stored file is not the document the corpus recorded.

    This is a corruption or substitution, and it must stop the load. Returning
    the text anyway would let an audit quote a document that is not the one its
    provenance describes.
    """

    def __init__(self, path: Path, expected: str, actual: str) -> None:
        super().__init__(
            f"Policy document hash mismatch: {path}\n"
            f"  expected {expected}\n"
            f"  actual   {actual}\n"
            f"  The file on disk is not the document this record describes. It "
            f"has been modified, truncated or replaced. Re-acquire it rather "
            f"than updating the recorded hash."
        )
        self.path = path
        self.expected = expected
        self.actual = actual


class PolicyDecodeError(PolicyDocumentError):
    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(f"Policy document could not be decoded as text: {path}\n  {detail}")
        self.path = path


def sha256_of_file(path: Path) -> str:
    """SHA-256 of a file's bytes, read in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def media_type_for(path: Path) -> str:
    return MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def load_policy_document(
    package_name: str,
    path: Path | str,
    source_url: str,
    expected_sha256: str | None = None,
    provenance: Provenance | None = None,
    encoding: str = "utf-8",
) -> PolicyDocument:
    """Load one stored policy document, verifying it.

    ``expected_sha256`` is the hash the corpus recorded. When given it is
    checked and a mismatch raises. When absent the hash is computed and
    returned, which is the import path: the first load is what establishes the
    hash the corpus will record.

    The file is opened read-only and is never written to.
    """
    path = Path(path)

    if not path.is_file():
        raise PolicyFileMissingError(path)

    data = path.read_bytes()
    actual = sha256_of_bytes(data)

    if expected_sha256 is not None and actual != expected_sha256:
        raise PolicyHashMismatchError(path, expected_sha256, actual)

    media_type = media_type_for(path)
    if media_type == "application/pdf":
        raise PolicyDecodeError(
            path,
            "PDF policies are stored but not decoded here. Text extraction "
            "from PDF is F-08 in Milestone 4; this loader returns text "
            "documents only.",
        )

    try:
        content = data.decode(encoding)
    except UnicodeDecodeError as exc:
        try:
            content = data.decode(encoding, errors="replace")
        except Exception:  # pragma: no cover - decode with replace cannot fail
            raise PolicyDecodeError(path, str(exc)) from exc
        # Decoding with replacement succeeded but lost characters. Say so
        # rather than passing damaged text silently into the pipeline.
        raise PolicyDecodeError(
            path,
            f"{exc}. The file is not valid {encoding}. Re-acquire it or record "
            f"its actual encoding; the pipeline must not analyse text with "
            f"replacement characters in it.",
        ) from exc

    return PolicyDocument(
        package_name=package_name,
        source_url=source_url,
        content=content,
        content_sha256=actual,
        storage_path=str(path),
        media_type=media_type,
        provenance=provenance,
    )


def verify_policy_file(path: Path | str, expected_sha256: str) -> bool:
    """Check a stored file against its recorded hash without loading the text."""
    path = Path(path)
    if not path.is_file():
        raise PolicyFileMissingError(path)
    return sha256_of_file(path) == expected_sha256
